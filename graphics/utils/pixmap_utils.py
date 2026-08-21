"""Utilities for generating pixmaps used in the node palette."""

from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtCore import Qt


def recolor_pixmap_black(pixmap: QPixmap) -> QPixmap:
    """Recolors the opaque content of a pixmap to solid black.

    Node sprites are drawn in light tones (designed for the canvas's
    dark background). In the light theme we use this recoloring to keep
    the outline visible against a white background, preserving the
    original alpha.
    """
    if not pixmap or pixmap.isNull():
        return pixmap

    colored = QPixmap(pixmap.size())
    colored.fill(Qt.GlobalColor.transparent)
    painter = QPainter(colored)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(colored.rect(), QColor(0, 0, 0))
    painter.end()
    return colored


def generate_pixmap_for_palette(
    icon_path: str, w: int = 60, h: int = 40, use_light_theme: bool = False
) -> QPixmap:
    """Generates a resized QPixmap for display in the node palette.

    Args:
        icon_path: Path to the icon image file.
        w: Maximum width in pixels.
        h: Maximum height in pixels.
        use_light_theme: If True, recolors the icon to black (same logic
            used for nodes drawn on the scene) so it stays visible against
            the palette's light background.

    Returns:
        Resized QPixmap keeping aspect ratio, with smooth transformation.
    """
    pixmap = QPixmap(icon_path)
    scaled = pixmap.scaled(
        w, h,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    if use_light_theme:
        return recolor_pixmap_black(scaled)
    return scaled
