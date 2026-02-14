from PyQt6.QtCore import QPointF

from graphics.items.base.nodes.switch.switch_item import SwitchItem
from .....anchors.anchor import AnchorItem


class ButtonSwitch(SwitchItem):

    SWITCH_VISUALS = {
        "NO": {
            0: {
                "sprite": "resources/nodes/button_switch/button_switch_no_open.png",
                "offset": QPointF(0, 0),
            },
            1: {
                "sprite": "resources/nodes/button_switch/button_switch_no_closed.png",
                "offset": QPointF(0, 0),
            },
        },
        "NC": {
            0: {
                "sprite": "resources/nodes/button_switch/button_switch_no_closed.png",
                "offset": QPointF(0, 0),
            },
            1: {
                "sprite": "resources/nodes/button_switch/button_switch_no_closed.png",
                "offset": QPointF(0, 0),
            },
        }
    }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.node_type = "button_switch"


    def initialize_anchors(self):
        self.add_anchor(AnchorItem("T", QPointF(self.width*39/50, 0), node=self, domain=self.domain))
        self.add_anchor(AnchorItem("B", QPointF(self.width*39/50, self.height), node=self, domain=self.domain))

    


    

