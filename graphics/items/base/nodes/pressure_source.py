from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF


from graphics.items.base.nodes.node_item import NodeItem
from ....anchors.anchor import AnchorItem


class PressureSource(NodeItem):
    def __init__(self):
        super().__init__()

        self.node_type = "pressure_source"
        

        self.pixmap = QPixmap("resources/nodes/pressure_source/pressure_source.png")

        self.width = self.pixmap.width()
        self.height = self.pixmap.height()

        # Anchors do node
        self.add_anchor(AnchorItem("P", QPointF(self.width*0.467, 0), node=self))