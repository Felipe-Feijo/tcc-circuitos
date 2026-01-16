from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QGridLayout
)
from PyQt6.QtCore import Qt
from graphics.ui.palette.component_palette_item import ComponentPaletteItem


class ComponentPalette(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(8)

        title = QLabel("Componentes")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        # área scrollável
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        main_layout.addWidget(scroll)

        # container interno com grid layout
        container = QWidget()
        self.grid_layout = QGridLayout(container)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setRowStretch(999, 1)
        self.grid_layout.setColumnStretch(999, 1)
        scroll.setWidget(container)

        # contador de linhas/colunas
        self.num_columns = 2  # ajuste conforme quiser

    def add_component(self, name: str, pixmap, callback):
        """
        Adiciona um item na grid e conecta clique.
        """
        item = ComponentPaletteItem(name, pixmap)

        # calcula posição na grid
        count = self.grid_layout.count()
        row = count // self.num_columns
        col = count % self.num_columns
        self.grid_layout.addWidget(item, row, col)

        # clique -> callback
        item.mouseReleaseEvent = lambda e, cb=callback: cb()