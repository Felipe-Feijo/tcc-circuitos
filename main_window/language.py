"""Runtime language switching (English / Portuguese-Brazil) via Qt Linguist.

Mirrors the persistence pattern already used by main_window/settings.py
(QSettings-backed, module-level get/apply functions).
"""

from pathlib import Path

from PyQt6.QtCore import QLocale, QObject, QSettings, QTranslator, pyqtSignal
from PyQt6.QtWidgets import QApplication

SUPPORTED_LANGUAGES = ("en", "pt_BR")
DEFAULT_LANGUAGE = "en"

_LANGUAGE_KEY = "ui/language"
_I18N_DIR = Path(__file__).resolve().parent.parent / "resources" / "i18n"


def _default_settings() -> QSettings:
    return QSettings("tcc-circuitos", "CircuitEditor")


def detect_system_language() -> str:
    """Returns "pt_BR" if the OS locale is Portuguese-Brazil, else "en"."""
    system_name = QLocale.system().name()  # e.g. "pt_BR", "en_US"
    return "pt_BR" if system_name.startswith("pt_BR") else DEFAULT_LANGUAGE


def get_language(settings: QSettings | None = None) -> str:
    """Returns the persisted language, or an OS-derived default if unset."""
    s = settings or _default_settings()
    stored = s.value(_LANGUAGE_KEY, None)
    if stored in SUPPORTED_LANGUAGES:
        return str(stored)
    return detect_system_language()


class LanguageManager(QObject):
    """Holds the currently installed QTranslator and notifies listeners
    (persistent widgets' retranslate_ui()) after a language switch."""

    language_changed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._translator: QTranslator | None = None

    def apply_language(
        self, app: QApplication, code: str, settings: QSettings | None = None
    ) -> None:
        if code not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language code: {code!r}")

        if self._translator is not None:
            app.removeTranslator(self._translator)
            self._translator = None

        # English needs no .qm: its tr() text IS the source text already.
        if code != DEFAULT_LANGUAGE:
            translator = QTranslator()
            qm_path = _I18N_DIR / f"circuiteditor_{code}.qm"
            if not translator.load(str(qm_path)):
                raise FileNotFoundError(
                    f"Translation file not found or invalid: {qm_path}"
                )
            app.installTranslator(translator)
            self._translator = translator

        s = settings or _default_settings()
        s.setValue(_LANGUAGE_KEY, code)

        self.language_changed.emit(code)


language_manager = LanguageManager()


def apply_language(
    app: QApplication, code: str, settings: QSettings | None = None
) -> None:
    """Convenience wrapper around the shared LanguageManager singleton."""
    language_manager.apply_language(app, code, settings)
