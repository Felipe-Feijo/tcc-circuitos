"""Nó gráfico de linha de pressão pneumática expansível."""

from graphics.items.base.nodes.expandable.expandable_item import ExpandableItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from PyQt6.QtCore import QPointF
from simulation.nodes.pressure_line import PressureLine as PressureLineNode


class PressureLine(ExpandableItem):
    node_type = "pressure_line"
    simulation_cls = PressureLineNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("pneumatic",),
            sprite="resources/nodes/pressure_line/pressure_line_terminal.png",
            name="Pressure Line",
        )
    TERMINAL_VISUALS = {
        "left":  "resources/nodes/pressure_line/pressure_line_terminal.png",
        "right": "resources/nodes/pressure_line/pressure_line_terminal.png"
    }
    DEFAULT_ANCHORS = ["X1", "X2"]
    ANCHOR_DIRECTIONS = {
        "first": {
            "external": ["left", "bottom"], 
            "internal": ["right"]
        },
        "middle": {
            "external": ["top", "bottom"], 
            "internal": ["left", "right"]
        },
        "last": {
            "external": ["right", "bottom"], 
            "internal": ["left"]
        }
    }
    def paint_symbol(self, painter):
        if not self.pixmap_left:
            return

        self.draw_pixmap(painter, QPointF(0, 0), self.pixmap_left)

        if self.pixmap_right:
            n = len(self.anchor_list)
            last_anchor_center = self.pix_w * 0.5 + (n - 1) * self.spacing
            pixmap_right_x = last_anchor_center - self.pix_w * 0.5

            self.draw_pixmap(painter, QPointF(int(pixmap_right_x), 0), self.pixmap_right)

    def layout_anchors(self):
        x0 = self.pix_w * 0.5
        y0 = self.pix_h

        for i, anchor in enumerate(self.anchor_list):
            br = anchor.boundingRect()
            cx = x0 + i * self.spacing
            cy = y0

            anchor.setPos(
                cx - br.center().x(),
                cy - br.center().y()
            )