from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGridLayout
from PyQt6.QtCore import Qt

from main_window.ui.palette.node_palette_item import NodePaletteItem


class PaletteSection(QWidget):
    def __init__(self, title: str, num_columns=2, parent=None):
        super().__init__(parent)

        self.title = title
        self.num_columns = num_columns
        self._collapsed = False

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(20)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Header clicável
        self.header = QLabel(f"▾ {title}")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setStyleSheet("font-weight: bold;")
        self.header.mousePressEvent = self.toggle

        self.main_layout.addWidget(self.header)

        # Container do grid
        self.content = QWidget()
        self.grid_layout = QGridLayout(self.content)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.main_layout.addWidget(self.content)

    def toggle(self, event=None):
        self._collapsed = not self._collapsed
        self.content.setVisible(not self._collapsed)
        self.header.setText(
            f"{'▸' if self._collapsed else '▾'} {self.title}"
        )

    def add_node(self, name: str, pixmap, callback):
        item = NodePaletteItem(name, pixmap)
        count = self.grid_layout.count()
        row = count // self.num_columns
        col = count % self.num_columns

        self.grid_layout.addWidget(item, row, col)

        item.mouseReleaseEvent = lambda e: callback()
        return item