from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QPen

class NodePaletteItem(QWidget):
    def __init__(self, name: str, pixmap, parent=None):
        super().__init__(parent)

        self.selected = False

        self.setFixedSize(100, 100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        image_label = QLabel()
        image_label.setPixmap(pixmap)
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        text_label = QLabel(name)
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

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