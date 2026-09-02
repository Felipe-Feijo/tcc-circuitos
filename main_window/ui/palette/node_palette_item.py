"""Individual palette item: component icon and name, draggable onto the scene."""

from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QPen
from graphics.utils.pixmap_utils import generate_pixmap_for_palette

DEFAULT_PIXMAP_WH = (60, 40)
DEFAULT_ITEM_WIDTH = 100


class NodePaletteItem(QWidget):
    def __init__(self, name: str, icon_path: str, parent=None):
        super().__init__(parent)

        self.selected = False
        self.icon_path = icon_path
        self.use_light_theme = False
        self._pixmap_wh = DEFAULT_PIXMAP_WH

        self.setFixedWidth(DEFAULT_ITEM_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(False)

        self.text_label = QLabel(name)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.text_label.setWordWrap(True)
        self.text_label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Minimum,
        )

        layout.addWidget(self.image_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.text_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.apply_size(DEFAULT_PIXMAP_WH, DEFAULT_ITEM_WIDTH, font_delta=0)

    def apply_size(self, pixmap_wh: tuple[int, int], item_width: int, font_delta: int):
        w, h = pixmap_wh
        self._pixmap_wh = pixmap_wh

        pixmap = generate_pixmap_for_palette(self.icon_path, w, h, self.use_light_theme)
        self.image_label.setPixmap(pixmap)
        self.image_label.setFixedSize(w, h)

        margins = self.layout().contentsMargins()
        content_width = item_width - margins.left() - margins.right()
        self.text_label.setFixedWidth(content_width)
        font = self.text_label.font()
        font.setPointSize(QApplication.instance().font().pointSize() + font_delta)
        self.text_label.setFont(font)

        self.setFixedWidth(item_width)

    def set_name(self, name: str):
        self.text_label.setText(name)

    def set_selected(self, value: bool):
        self.selected = value
        self.update()

    def set_light_theme(self, is_light: bool):
        self.use_light_theme = is_light
        w, h = self._pixmap_wh
        pixmap = generate_pixmap_for_palette(self.icon_path, w, h, self.use_light_theme)
        self.image_label.setPixmap(pixmap)

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
