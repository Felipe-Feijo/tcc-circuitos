"""Utilitários para geração de pixmaps usados na paleta de nós."""

from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtCore import Qt


def recolor_pixmap_black(pixmap: QPixmap) -> QPixmap:
    """Recolore o conteúdo opaco de um pixmap para preto sólido.

    Os sprites dos nós são desenhados em tons claros (pensados pro fundo
    dark do canvas). No tema light usamos essa recoloração pra manter o
    contorno visível sobre fundo branco, preservando o alpha original.
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
    """Gera um QPixmap redimensionado para exibição na paleta de nós.

    Args:
        icon_path: Caminho para o arquivo de imagem do ícone.
        w: Largura máxima em pixels.
        h: Altura máxima em pixels.
        use_light_theme: Se True, recolore o ícone pra preto (mesma lógica
            usada nos nós desenhados na cena) pra ficar visível sobre o
            fundo claro da paleta.

    Returns:
        QPixmap redimensionado mantendo proporção, com transformação suave.
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
