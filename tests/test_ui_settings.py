# tests/test_ui_settings.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QWidget
app = QApplication.instance() or QApplication([])

from PyQt6.QtCore import QSettings
import main_window.settings as settings


def _ini_settings(tmp_path):
    """QSettings backed by a throwaway .ini file, so tests never touch
    the real user's registry/settings store."""
    return QSettings(str(tmp_path / "test_settings.ini"), QSettings.Format.IniFormat)


def test_get_font_size_default(tmp_path):
    s = _ini_settings(tmp_path)
    assert settings.get_font_size(s) == settings.DEFAULT_FONT_SIZE


def test_set_and_get_font_size_roundtrip(tmp_path):
    s = _ini_settings(tmp_path)
    settings.set_font_size(16, s)
    assert settings.get_font_size(s) == 16


def test_get_palette_tier_default(tmp_path):
    s = _ini_settings(tmp_path)
    assert settings.get_palette_tier(s) == settings.DEFAULT_PALETTE_TIER


def test_set_and_get_palette_tier_roundtrip(tmp_path):
    s = _ini_settings(tmp_path)
    settings.set_palette_tier("large", s)
    assert settings.get_palette_tier(s) == "large"


def test_apply_font_from_settings_sets_app_font(tmp_path):
    s = _ini_settings(tmp_path)
    settings.set_font_size(18, s)
    settings.apply_font_from_settings(app, s)
    assert app.font().pointSize() == 18


def test_prompt_and_apply_font_size_accept(tmp_path, monkeypatch):
    s = _ini_settings(tmp_path)
    monkeypatch.setattr(
        "main_window.settings.QInputDialog.getInt",
        lambda *a, **kw: (15, True),
    )
    parent = QWidget()
    changed = settings.prompt_and_apply_font_size(parent, s)
    assert changed is True
    assert app.font().pointSize() == 15
    assert settings.get_font_size(s) == 15


def test_prompt_and_apply_font_size_cancel(tmp_path, monkeypatch):
    s = _ini_settings(tmp_path)
    settings.set_font_size(12, s)
    monkeypatch.setattr(
        "main_window.settings.QInputDialog.getInt",
        lambda *a, **kw: (99, False),
    )
    parent = QWidget()
    changed = settings.prompt_and_apply_font_size(parent, s)
    assert changed is False
    assert settings.get_font_size(s) == 12
