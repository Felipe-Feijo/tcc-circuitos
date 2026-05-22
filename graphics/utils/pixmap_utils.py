"""Utilitários para geração de pixmaps usados na paleta de nós."""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt


def generate_pixmap_for_palette(icon_path: str, w: int = 60, h: int = 40) -> QPixmap:
    """Gera um QPixmap redimensionado para exibição na paleta de nós.

    Args:
        icon_path: Caminho para o arquivo de imagem do ícone.
        w: Largura máxima em pixels.
        h: Altura máxima em pixels.

    Returns:
        QPixmap redimensionado mantendo proporção, com transformação suave.
    """
    pixmap = QPixmap(icon_path)
    return pixmap.scaled(
        w, h,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
