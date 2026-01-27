from PyQt6.QtCore import QPointF

from graphics.items.base.nodes.directional_valve.directional_valve_item import DirectionalValveItem
from .....anchors.anchor import AnchorItem


class Valve_4_2_Ways(DirectionalValveItem):
    BODY_VISUALS = {
        0: {  # repouso
            "sprite": "resources/nodes/valve_4_2_ways/valve_4_2_body_right.png",
            "offset": QPointF(0, 0),
        },
        1: {  # ativo
            "sprite": "resources/nodes/valve_4_2_ways/valve_4_2_body_left.png",
            "offset": QPointF(147, 0),
        }
    }
    def __init__(self):
        super().__init__()

        self.node_type = "valve_4_2_ways"


    def initialize_anchors(self):
        # Anchors nos cantos do body
        self.add_anchor(AnchorItem("P", QPointF(self.width*191/300, self.height), node=self))        
        self.add_anchor(AnchorItem("A", QPointF(self.width*191/300, 0), node=self))   
        self.add_anchor(AnchorItem("B", QPointF(self.width*256/300, 0), node=self))  
        self.add_anchor(AnchorItem("R", QPointF(self.width*256/300, self.height), node=self))    