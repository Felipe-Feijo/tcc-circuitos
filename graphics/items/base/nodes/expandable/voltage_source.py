from graphics.items.base.nodes.expandable.expandable_item import ExpandableItem
from PyQt6.QtCore import QPointF
from simulation.nodes.voltage_source import VoltageSource as VoltageSourceNode

class VoltageSource(ExpandableItem):
    node_type = "voltage_source"
    simulation_cls = VoltageSourceNode
    TERMINAL_VISUALS = {
        "left":  "resources/nodes/voltage_source/voltage_source_terminal.png",
    }
    DEFAULT_ANCHORS = ["X1"]
    ANCHOR_DIRECTIONS = {
        "single": {
            "external": ["left", "bottom", "top"],
        },
        "first": {
            "external": ["bottom", "top"], 
            "internal": ["right"]
        },
        "middle": {
            "external": ["top", "bottom"], 
            "internal": ["left", "right"]
        },
        "last": {
            "external": ["right", "top", "bottom"], 
            "internal": ["left"]
        }
    }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


    def paint_symbol(self, painter):
        if not self.pixmap_left:
            return

        self.draw_pixmap(painter, QPointF(0, 0), self.pixmap_left)

    def layout_anchors(self):
        x0 = self.pix_w
        y0 = self.pix_h * 69/100

        for i, anchor in enumerate(self.anchor_list):
            br = anchor.boundingRect()
            cx = x0 + i * self.spacing
            cy = y0

            anchor.setPos(
                cx - br.center().x(),
                cy - br.center().y()
            )