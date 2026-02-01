from PyQt6.QtCore import QPointF
from graphics.anchors.anchor import AnchorItem
from graphics.items.base.nodes.piston.piston_item import PistonItem

class SimplePiston(PistonItem):

    BODY_VISUALS = {
        0: {
            "sprite": "resources/nodes/piston/piston.png",
            "offset": QPointF(0, 0),
        },
        1: {
            "sprite": "resources/nodes/piston/piston_extended.png",
            "offset": QPointF(0, 0),
        }
    }

    def __init__(self):
        super().__init__()

        self.node_type = "piston"

    def initialize_anchors(self):
        self.add_anchor(AnchorItem("A", QPointF(self.width * 0.0621, self.height), node=self))