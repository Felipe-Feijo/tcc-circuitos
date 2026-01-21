import os
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF


from graphics.items.base.nodes.node_item import NodeItem
from ....anchors.anchor import AnchorItem


class PressureSource(NodeItem):
    def __init__(self, icon_path="resources/nodes/pressure_source/pressure_source.png"):
        super().__init__()

        self.node_type = "pressure_source"
        

        if icon_path and os.path.isfile(icon_path):
            self.pixmap = QPixmap(icon_path)

        self.width = self.pixmap.width()
        self.height = self.pixmap.height()

        # Anchors do node
        self.add_anchor(AnchorItem("P", QPointF(self.width*0.467, 0), node=self))