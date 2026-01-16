from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

def generate_pixmap_for_palette(icon_path, w=60, h=40):
    """
    Gera um QPixmap escalado para mostrar na palette.
    """
    pixmap = QPixmap(icon_path)
    return pixmap.scaled(
        w, h,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation
    )