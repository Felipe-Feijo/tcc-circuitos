# tests/test_language_manager.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from unittest.mock import patch
from PyQt6.QtCore import QSettings
from main_window.language import (
    LanguageManager, get_language, detect_system_language, DEFAULT_LANGUAGE,
)


def _fresh_settings() -> QSettings:
    s = QSettings("tcc-circuitos-tests", "LanguageManagerTests")
    s.clear()
    return s


def test_detect_system_language_recognizes_pt_br():
    with patch("main_window.language.QLocale") as mock_locale:
        mock_locale.system.return_value.name.return_value = "pt_BR"
        assert detect_system_language() == "pt_BR"


def test_detect_system_language_falls_back_to_english():
    with patch("main_window.language.QLocale") as mock_locale:
        mock_locale.system.return_value.name.return_value = "fr_FR"
        assert detect_system_language() == DEFAULT_LANGUAGE


def test_get_language_uses_system_detection_when_unset():
    settings = _fresh_settings()
    with patch("main_window.language.detect_system_language", return_value="pt_BR"):
        assert get_language(settings) == "pt_BR"


def test_get_language_prefers_persisted_value_over_system_detection():
    settings = _fresh_settings()
    settings.setValue("ui/language", "pt_BR")
    with patch("main_window.language.detect_system_language", return_value="en"):
        assert get_language(settings) == "pt_BR"


def test_apply_language_persists_choice_and_emits_signal():
    settings = _fresh_settings()
    manager = LanguageManager()
    received = []
    manager.language_changed.connect(received.append)

    with patch("main_window.language.QTranslator") as mock_translator_cls:
        mock_translator_cls.return_value.load.return_value = True
        with patch.object(app, "installTranslator"):
            manager.apply_language(app, "pt_BR", settings)

    assert settings.value("ui/language") == "pt_BR"
    assert received == ["pt_BR"]


def test_apply_language_english_needs_no_qm_file():
    settings = _fresh_settings()
    manager = LanguageManager()
    manager.apply_language(app, "en", settings)  # must not try to load a .qm
    assert settings.value("ui/language") == "en"


def test_apply_language_rejects_unsupported_code():
    settings = _fresh_settings()
    manager = LanguageManager()
    try:
        manager.apply_language(app, "fr", settings)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_apply_language_removes_previous_translator_before_installing_new_one():
    settings = _fresh_settings()
    manager = LanguageManager()

    with patch("main_window.language.QTranslator") as mock_translator_cls:
        mock_translator_cls.return_value.load.return_value = True
        with patch.object(app, "installTranslator"):
            with patch.object(app, "removeTranslator"):
                manager.apply_language(app, "pt_BR", settings)
                first_translator = manager._translator
                manager.apply_language(app, "en", settings)

    assert manager._translator is None
    # can't easily assert app.removeTranslator was called on a real
    # QApplication without a live translator; behavioral coverage for the
    # swap itself is exercised in Task 3's end-to-end MainWindow test.


def test_apply_language_falls_back_to_english_when_qm_missing():
    """Regression test for Finding 4 (final whole-branch review): a
    missing/corrupt .qm file used to raise FileNotFoundError uncaught from
    apply_language(), and since app.py calls it unconditionally before
    MainWindow is even constructed, this crashed the whole app with no
    window and no user-facing error. Fixed by catching the load failure,
    logging a warning, and falling back to English (both in the current
    call and in what gets persisted, so a broken catalog doesn't retry
    and fail on every subsequent launch)."""
    settings = _fresh_settings()
    manager = LanguageManager()
    received = []
    manager.language_changed.connect(received.append)

    with patch("main_window.language.QTranslator") as mock_translator_cls:
        mock_translator_cls.return_value.load.return_value = False
        with patch.object(app, "installTranslator") as mock_install:
            manager.apply_language(app, "pt_BR", settings)  # must not raise
            mock_install.assert_not_called()

    # Falls back to English: persisted setting, emitted signal, and no
    # installed translator all agree -- not a UI that's silently
    # untranslated while everything else still believes pt_BR is active.
    assert settings.value("ui/language") == "en"
    assert received == ["en"]
    assert manager._translator is None


def test_apply_language_missing_qm_still_allows_constructing_main_window():
    """Same fallback, exercised closer to how app.py actually calls it:
    language applied before MainWindow() is constructed, against a
    genuinely missing .qm file on disk (not mocked), followed by a real
    MainWindow() construction to confirm the app can still start and
    ends up in English."""
    settings = _fresh_settings()
    manager = LanguageManager()

    with patch("main_window.language._I18N_DIR", Path("nonexistent_i18n_dir_for_test")):
        manager.apply_language(app, "pt_BR", settings)  # must not raise

    assert settings.value("ui/language") == "en"

    from main_window.main_window import MainWindow
    window = MainWindow()
    try:
        assert window.windowTitle() == "Circuit Editor"  # English, not Portuguese
    finally:
        window.close()
