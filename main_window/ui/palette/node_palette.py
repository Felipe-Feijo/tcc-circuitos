from PyQt6.QtWidgets import ( QWidget, QVBoxLayout, QLabel, QScrollArea, QGridLayout ) 
from PyQt6.QtCore import Qt 
from main_window.ui.palette.node_palette_item import NodePaletteItem 

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
    
        # container interno com grid layout 
        container = QWidget() 
        self.grid_layout = QGridLayout(container) 
        self.grid_layout.setSpacing(8) 
        self.grid_layout.setRowStretch(999, 1) 
        self.grid_layout.setColumnStretch(999, 1) 
        scroll.setWidget(container) 

        # contador de linhas/colunas 
        self.num_columns = 2 
        
        # ajuste conforme quiser 
        self.selected_item: NodePaletteItem | None = None 
        
    def add_node(self, name: str, pixmap, callback): 
        item = NodePaletteItem(name, pixmap) 
        count = self.grid_layout.count() 
        row = count // self.num_columns 
        col = count % self.num_columns 
        self.grid_layout.addWidget(item, row, col) 
        

        item.mouseReleaseEvent = lambda e: self.on_click(item, callback) 
        
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