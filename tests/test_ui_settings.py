# tests/test_ui_settings.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QWidget
app = QApplication.instance() or QApplication([])

import pytest

from PyQt6.QtCore import QSettings
import main_window.settings as settings


@pytest.fixture(autouse=True)
def _restore_app_font():
    original = app.font()
    yield
    app.setFont(original)


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


def test_get_font_size_falls_back_on_non_numeric_value(tmp_path):
    s = _ini_settings(tmp_path)
    s.setValue(settings._FONT_SIZE_KEY, "not-a-number")
    assert settings.get_font_size(s) == settings.DEFAULT_FONT_SIZE


def test_get_font_size_clamps_out_of_range_high_value(tmp_path):
    s = _ini_settings(tmp_path)
    s.setValue(settings._FONT_SIZE_KEY, 999)
    assert settings.get_font_size(s) == settings.MAX_FONT_SIZE


def test_get_font_size_clamps_out_of_range_low_value(tmp_path):
    s = _ini_settings(tmp_path)
    s.setValue(settings._FONT_SIZE_KEY, 0)
    assert settings.get_font_size(s) == settings.MIN_FONT_SIZE
