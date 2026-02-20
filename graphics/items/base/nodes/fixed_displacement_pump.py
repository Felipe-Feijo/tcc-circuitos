from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF


from graphics.items.base.nodes.node_item import NodeItem
from ....anchors.anchor import AnchorItem


class FixedDisplacementPump(NodeItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.node_type = "fixed_displacement_pump"
        

        self.pixmap = QPixmap("resources/nodes/fixed_displacement_pump/fixed_displacement_pump.png")

        self.width = self.pixmap.width()
        self.height = self.pixmap.height()

        # Anchors do node
        self.add_anchor(AnchorItem("S", QPointF(self.width*28/84, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom", "right", "left"]}))
        self.add_anchor(AnchorItem("P", QPointF(self.width*28/84, 0), node=self, domain=self.domain, exit_directions={"external": ["top", "right", "left"]}))