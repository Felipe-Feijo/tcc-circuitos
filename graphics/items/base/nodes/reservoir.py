from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF


from graphics.items.base.nodes.node_item import NodeItem
from ....anchors.anchor import AnchorItem


class Reservoir(NodeItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.node_type = "reservoir"
        

        self.pixmap = QPixmap("resources/nodes/reservoir/reservoir.png")

        self.width = self.pixmap.width()
        self.height = self.pixmap.height()

        # Anchors do node
        self.add_anchor(AnchorItem("R", QPointF(self.width*0.5, self.height*0.95), node=self, domain=self.domain, exit_directions={"external": ["top"]}))