"""Global application theme (QPalette + QSS) for dark/light mode.

The theme toggle used to only affect the QGraphicsView background and
the scene items (nodes/connections/labels, via EditorState.theme_changed).
Toolbar, menus, docks and dialogs were left out, inheriting the OS/Qt
default QPalette -- which is why they always looked "dark" and didn't
react to the toggle.

This module centralizes the definition of both palettes and injects the
corresponding QSS, so that `set_light_theme()` can apply the theme to
the whole QApplication, not just the canvas.
"""

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

_STYLES_DIR = Path(__file__).resolve().parent.parent / "resources"


def _dark_palette() -> QPalette:
    window = QColor(45, 45, 45)
    # QPalette(color) derives Light/Midlight/Dark/Mid/Shadow from a single
    # base color, so the native style's 3D bevels (QPushButton, QSpinBox
    # arrows) stay internally consistent -- an empty QPalette() leaves
    # those roles at Qt's compiled-in defaults, unrelated to `window`.
    palette = QPalette(window)
    base = QColor(30, 30, 30)
    text = QColor(220, 220, 220)
    disabled_text = QColor(127, 127, 127)
    highlight = QColor(70, 130, 180)

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, window)
    palette.setColor(QPalette.ColorRole.ToolTipBase, text)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, window)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 80, 80))
    palette.setColor(QPalette.ColorRole.Link, highlight)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    # QPalette(color) also derives Accent -- the role "windows11" paints
    # checked checkboxes/radio buttons/sliders with -- as a shade of
    # `window`, which came out pure black here. Pin it to the same color
    # as Highlight instead (reported: checked checkboxes rendered with
    # no visible check at all).
    palette.setColor(QPalette.ColorRole.Accent, highlight)

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text)
    return palette


def _light_palette() -> QPalette:
    window = QColor(240, 240, 240)
    palette = QPalette(window)  # see _dark_palette() for why
    base = QColor(255, 255, 255)
    text = QColor(20, 20, 20)
    disabled_text = QColor(150, 150, 150)
    highlight = QColor(70, 130, 180)

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, window)
    palette.setColor(QPalette.ColorRole.ToolTipBase, window)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, window)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor(200, 0, 0))
    palette.setColor(QPalette.ColorRole.Link, highlight)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    # See _dark_palette() -- QPalette(color) derives Accent as a shade of
    # `window`, which came out pure white here (matching Base), so
    # checked checkboxes rendered as a blank white square instead of a
    # visible check.
    palette.setColor(QPalette.ColorRole.Accent, highlight)

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text)
    return palette


def _stylesheet_path(is_light: bool) -> Path:
    name = "styles_light.qss" if is_light else "styles_dark.qss"
    return _STYLES_DIR / name


def apply_theme(app: QApplication, is_light: bool) -> None:
    """Applies the theme palette + stylesheet to the whole QApplication.

    Covers native widgets with no explicit QSS rule (dialogs, docks,
    menus) via QPalette, and the custom styles (toolbar hover/checked,
    sizeTierButton) via QSS.

    The "windows11" style (Qt's default on Windows 11) draws standard
    controls -- QPushButton, QSpinBox/QDoubleSpinBox arrows, checkboxes,
    comboboxes -- from the OS-reported color scheme
    (QStyleHints.colorScheme()), not from QPalette. Without this,
    toggling the app's light/dark theme leaves those controls stuck
    following the OS setting -- e.g. dark-mode button chrome rendered
    over a light dialog when Windows is in dark mode but the app is set
    to light (reported: OK/Cancel and the Δt spin box looked "washed
    out" and didn't match the light dialog background). Forces the
    style's own scheme to follow the app's theme instead.
    """
    app.styleHints().setColorScheme(Qt.ColorScheme.Light if is_light else Qt.ColorScheme.Dark)
    app.setPalette(_light_palette() if is_light else _dark_palette())
    with open(_stylesheet_path(is_light), "r", encoding="utf-8") as f:
        app.setStyleSheet(f.read())
