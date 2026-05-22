"""Item individual da paleta: ícone e nome do componente, arrastável para a cena."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QPen

class NodePaletteItem(QWidget):
    def __init__(self, name: str, pixmap, parent=None):
        super().__init__(parent)

        self.selected = False

        self.setFixedWidth(100)
        # altura não é fixada — cresce com o texto

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        image_label = QLabel()
        image_label.setPixmap(pixmap)
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_label.setFixedHeight(60)

        text_label = QLabel(name)
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop)
        text_label.setWordWrap(True)
        text_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum,
        )

        layout.addWidget(image_label)
        layout.addWidget(text_label)

        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_selected(self, value: bool):
        self.selected = value
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)

        if not self.selected:
            return

        painter = QPainter(self)
        pen = QPen(Qt.GlobalColor.blue, 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.drawRoundedRect(rect, 6, 6)
