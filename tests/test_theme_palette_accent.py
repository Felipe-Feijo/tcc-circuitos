"""Regression: QPalette::Accent -- the role Qt's native "windows11" style
uses to paint checked checkboxes/radio buttons/sliders -- was left to
whatever `QPalette(window)` auto-derives (pure white in the light theme),
instead of the app's own selection color. That made every checked
checkbox in a properties dialog render blank/white instead of blue
(reported: "os botões de seleção nos dialogs não estão ficando com o
check azul quando selecionado"). Verified against a rendered QCheckBox
pixel before writing this: `Accent` unset -> style falls back to a
native blue; `Accent` derived to white by `QPalette(window)` -> checked
box renders flat white; `Accent` explicitly set -> checked box renders
that color, in both themes.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from main_window.theme import _light_palette, _dark_palette


def test_light_palette_accent_matches_highlight_not_derived_white():
    palette = _light_palette()
    accent = palette.color(QPalette.ColorRole.Accent)
    assert accent == palette.color(QPalette.ColorRole.Highlight)
    assert accent != palette.color(QPalette.ColorRole.Base)


def test_dark_palette_accent_matches_highlight():
    palette = _dark_palette()
    accent = palette.color(QPalette.ColorRole.Accent)
    assert accent == palette.color(QPalette.ColorRole.Highlight)
