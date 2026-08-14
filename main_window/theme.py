"""Tema global da aplicação (QPalette + QSS) para dark/light mode.

O toggle de tema historicamente só afetava o fundo do QGraphicsView e os
itens da cena (nodes/connections/labels, via EditorState.theme_changed).
Toolbar, menus, docks e diálogos ficavam de fora, herdando a QPalette
padrão do SO/Qt -- por isso pareciam sempre "dark" e não reagiam ao toggle.

Este módulo centraliza a definição das duas paletas e injeta o QSS
correspondente, para que `set_light_theme()` consiga aplicar o tema na
QApplication inteira, não só no canvas.
"""

from pathlib import Path

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

_STYLES_DIR = Path(__file__).resolve().parent.parent / "resources"


def _dark_palette() -> QPalette:
    palette = QPalette()
    window = QColor(45, 45, 45)
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

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text)
    return palette


def _light_palette() -> QPalette:
    palette = QPalette()
    window = QColor(240, 240, 240)
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

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text)
    return palette


def _stylesheet_path(is_light: bool) -> Path:
    name = "styles_light.qss" if is_light else "styles_dark.qss"
    return _STYLES_DIR / name


def apply_theme(app: QApplication, is_light: bool) -> None:
    """Aplica paleta + stylesheet de tema na QApplication inteira.

    Cobre widgets nativos sem regra explícita no QSS (diálogos, docks,
    menus) via QPalette, e os estilos customizados (hover/checked de
    toolbar, sizeTierButton) via QSS.
    """
    app.setPalette(_light_palette() if is_light else _dark_palette())
    with open(_stylesheet_path(is_light), "r", encoding="utf-8") as f:
        app.setStyleSheet(f.read())
