from PyQt6.QtCore import QPointF

from graphics.items.base.nodes.directional_valve.directional_valve_item import DirectionalValveItem
from .....anchors.anchor import AnchorItem


class Valve_3_2_Ways(DirectionalValveItem):
    BODY_VISUALS = {
        0: {  # repouso
            "sprite": "resources/nodes/valve_3_2_ways/valve_3_2_body_right.png",
            "offset": QPointF(0, 0),
        },
        1: {  # ativo
            "sprite": "resources/nodes/valve_3_2_ways/valve_3_2_body_left.png",
            "offset": QPointF(147, 0),
        }
    }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.node_type = "valve_3_2_ways"


    def initialize_anchors(self):
        self.add_anchor(AnchorItem("A", QPointF(self.width*254/300, 0), node=self, domain=self.domain))
        self.add_anchor(AnchorItem("R", QPointF(self.width*190/300, self.height), node=self, domain=self.domain))
        self.add_anchor(AnchorItem("P", QPointF(self.width*254/300, self.height), node=self, domain=self.domain))

    


    

