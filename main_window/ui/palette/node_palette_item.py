from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt

class NodePaletteItem(QWidget):
    def __init__(self, name: str, pixmap, parent=None):
        super().__init__(parent)

        self.setFixedSize(100, 100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # sprite
        image_label = QLabel()
        image_label.setPixmap(pixmap)
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # nome / caminho
        text_label = QLabel(name)
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(image_label)
        layout.addWidget(text_label)

        # cursor muda ao passar
        self.setCursor(Qt.CursorShape.PointingHandCursor)