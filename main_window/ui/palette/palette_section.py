"""Palette grouping section (e.g. "Pneumatic", "Electric")."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGridLayout
from PyQt6.QtCore import Qt

from main_window.ui.palette.node_palette_item import NodePaletteItem


class PaletteSection(QWidget):
    def __init__(self, title: str, num_columns=2, parent=None):
        super().__init__(parent)

        self.title = title
        self.num_columns = num_columns
        self._collapsed = False
        self._items: list[NodePaletteItem] = []

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(20)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Clickable header
        self.header = QLabel()
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setStyleSheet("font-weight: bold;")
        self.header.mousePressEvent = self.toggle
        self._refresh_header_text()

        self.main_layout.addWidget(self.header)

        # Grid container
        self.content = QWidget()
        self.grid_layout = QGridLayout(self.content)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.main_layout.addWidget(self.content)

    def _refresh_header_text(self):
        arrow = "▸" if self._collapsed else "▾"
        self.header.setText(f"{arrow} {self.title}")

    def toggle(self, event=None):
        self._collapsed = not self._collapsed
        self.content.setVisible(not self._collapsed)
        self._refresh_header_text()

    def retranslate_ui(self, title: str):
        """Updates the displayed title (called after a language change;
        title is already translated by the caller)."""
        self.title = title
        self._refresh_header_text()

    def add_node(self, name: str, icon_path: str, callback):
        item = NodePaletteItem(name, icon_path)
        self._items.append(item)
        self._place_item(item, len(self._items) - 1)

        item.mouseReleaseEvent = lambda e: callback()
        return item

    def _place_item(self, item: NodePaletteItem, index: int):
        row = index // self.num_columns
        col = index % self.num_columns
        self.grid_layout.addWidget(item, row, col)

    def set_num_columns(self, cols: int):
        if cols == self.num_columns or cols < 1:
            return
        self.num_columns = cols

        while self.grid_layout.count():
            self.grid_layout.takeAt(0)

        for index, item in enumerate(self._items):
            self._place_item(item, index)

    def apply_item_size(self, pixmap_wh: tuple[int, int], item_width: int, font_delta: int):
        for item in self._items:
            item.apply_size(pixmap_wh, item_width, font_delta)

    def set_light_theme(self, is_light: bool):
        for item in self._items:
            item.set_light_theme(is_light)