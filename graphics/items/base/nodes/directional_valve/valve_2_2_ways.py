"""Graphics node for the 2/2-way directional valve."""

from PyQt6.QtCore import QPointF
from simulation.nodes.directional_valve.valve_2_2_ways import Valve_2_2_Ways as Valve_2_2_WaysNode

from graphics.items.base.nodes.directional_valve.directional_valve_item import DirectionalValveItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from .....anchors.anchor import AnchorItem


class Valve_2_2_Ways(DirectionalValveItem):
    node_type = "valve_2_2_ways"
    simulation_cls = Valve_2_2_WaysNode
    BODY_VISUALS = {
        0: {  # repouso (normalmente fechada)
            "sprite": "resources/nodes/valve_2_2_ways/valve_2_2_body_right.png",
            "offset": QPointF(0, 0),
        },
        1: {  # ativa (aberta)
            "sprite": "resources/nodes/valve_2_2_ways/valve_2_2_body_left.png",
            "offset": QPointF(147, 0),
        }
    }

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("pneumatic", "hydraulic"),
            sprite=cls.BODY_VISUALS[0]["sprite"],
            name="Valve 2/2 Ways",
        )

    def initialize_anchors(self):
        self.add_anchor(AnchorItem("A", QPointF(self.width * 224.5 / 300, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))
        self.add_anchor(AnchorItem("P", QPointF(self.width * 224.5 / 300, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))
