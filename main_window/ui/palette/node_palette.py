"""Widget da paleta de nós com scroll e organização em seções."""

from PyQt6.QtWidgets import ( QWidget, QVBoxLayout, QLabel, QScrollArea, QGridLayout ) 
from PyQt6.QtCore import Qt 
from main_window.ui.palette.node_palette_item import NodePaletteItem
from main_window.ui.palette.palette_section import PaletteSection 

class NodePalette(QWidget): 
    def __init__(self, parent=None): 
        super().__init__(parent) 
        main_layout = QVBoxLayout(self) 
        main_layout.setContentsMargins(4, 4, 4, 4) 
        main_layout.setSpacing(8) 
        title = QLabel("Nodes") 
        title.setAlignment(Qt.AlignmentFlag.AlignCenter) 
        main_layout.addWidget(title) 
    
        # área scrollável 
        scroll = QScrollArea() 
        scroll.setWidgetResizable(True) 
        main_layout.addWidget(scroll) 

        self.sections = {}
    
        # container interno com grid layout 
        container = QWidget() 
        self.container_layout = QVBoxLayout(container)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.container_layout.setSpacing(8)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(container) 

        # contador de linhas/colunas 
        self.num_columns = 2 
        
        # ajuste conforme quiser 
        self.selected_item: NodePaletteItem | None = None 
        
    def on_click(self, item, callback): 
        self.select_item(item) 
        callback() 
        
    def select_item(self, item: NodePaletteItem): 
        if self.selected_item is item: 
            return 
        if self.selected_item: 
            self.selected_item.set_selected(False) 
        self.selected_item = item 
        item.set_selected(True) 
        
    def clear_selection(self): 
        if self.selected_item: 
            self.selected_item.set_selected(False) 
        self.selected_item = None

    def add_section(self, name: str):
        if name in self.sections:
            return self.sections[name]

        section = PaletteSection(name, num_columns=self.num_columns)
        self.sections[name] = section
        self.container_layout.addWidget(section)
        return section

    def register_item(self, item: NodePaletteItem, callback):
        item.mouseReleaseEvent = lambda e: self.on_click(item, callback)