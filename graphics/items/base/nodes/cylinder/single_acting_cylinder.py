from PyQt6.QtCore import QPointF
from graphics.anchors.anchor import AnchorItem
from graphics.items.base.nodes.cylinder.cylinder_item import CylinderItem

class SingleActingCylinder(CylinderItem):

    BODY_VISUALS = {
        0: {
            "sprite": "resources/nodes/single_acting_cylinder/single_acting_cylinder_retracted.png",
            "offset": QPointF(0, 0),
        },
        1: {
            "sprite": "resources/nodes/single_acting_cylinder/single_acting_cylinder_extended.png",
            "offset": QPointF(0, 0),
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.node_type = "single_acting_cylinder"

    def initialize_anchors(self):
        self.add_anchor(AnchorItem("A", QPointF(self.width * 18/360, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))