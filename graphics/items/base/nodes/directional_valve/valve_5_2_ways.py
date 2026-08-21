"""Graphics node for the 5/2-way directional valve."""

from PyQt6.QtCore import QPointF
from simulation.nodes.directional_valve.valve_5_2_ways import Valve_5_2_Ways as Valve_5_2_WaysNode

from graphics.items.base.nodes.directional_valve.directional_valve_item import DirectionalValveItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from .....anchors.anchor import AnchorItem


class Valve_5_2_Ways(DirectionalValveItem):
    node_type = "valve_5_2_ways"
    simulation_cls = Valve_5_2_WaysNode
    BODY_VISUALS = {
        0: {  # rest
            "sprite": "resources/nodes/valve_5_2_ways/valve_5_2_body_right.png",
            "offset": QPointF(0, 0),
        },
        1: {  # active
            "sprite": "resources/nodes/valve_5_2_ways/valve_5_2_body_left.png",
            "offset": QPointF(222, 0),
        }
    }

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("pneumatic", "hydraulic"),
            sprite=cls.BODY_VISUALS[0]["sprite"],
            name="Valve 5/2 Ways",
        )

    def initialize_anchors(self):
        # Top ports: A (cylinder extension outlet) and B (cylinder retraction outlet)
        # Bottom ports: P (pressure), R1 (side A exhaust), R2 (side B exhaust)
        self.add_anchor(AnchorItem("P",  QPointF(self.width * 338/450, self.height),  node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))
        self.add_anchor(AnchorItem("A",  QPointF(self.width * 270/450, 0),            node=self, domain=self.domain, exit_directions={"external": ["top"]}))
        self.add_anchor(AnchorItem("B",  QPointF(self.width * 405/450, 0),            node=self, domain=self.domain, exit_directions={"external": ["top"]}))
        self.add_anchor(AnchorItem("R1", QPointF(self.width * 271/450, self.height),  node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))
        self.add_anchor(AnchorItem("R2", QPointF(self.width * 405/450, self.height),  node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))
