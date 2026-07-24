"""Nó gráfico de válvula direcional 4/3 vias, centro fechado."""

from PyQt6.QtCore import QPointF
from simulation.nodes.directional_valve.valve_4_3_ways import Valve_4_3_Ways as Valve_4_3_WaysNode

from graphics.items.base.nodes.directional_valve.directional_valve_item import DirectionalValveItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from .....anchors.anchor import AnchorItem


class Valve_4_3_Ways(DirectionalValveItem):
    node_type = "valve_4_3_ways"
    simulation_cls = Valve_4_3_WaysNode
    THREE_POSITION = True

    BODY_VISUALS = {
        # Offsets medidos em relação ao centro (state 1), que é a referência
        # (offset 0) -- não em relação ao state 0, como nas válvulas 2-posições.
        0: {  # ativo-direita
            "sprite": "resources/nodes/valve_4_3_ways/valve_4_3_body_right.png",
            "offset": QPointF(-150, 0),
        },
        1: {  # centro (repouso) -- referência
            "sprite": "resources/nodes/valve_4_3_ways/valve_4_3_body_middle.png",
            "offset": QPointF(0, 0),
        },
        2: {  # ativo-esquerda
            "sprite": "resources/nodes/valve_4_3_ways/valve_4_3_body_left.png",
            "offset": QPointF(147, 0),
        },
    }

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("pneumatic", "hydraulic"),
            sprite=cls.BODY_VISUALS[1]["sprite"],
            name="Valve 4/3 Ways",
        )

    def initialize_anchors(self):
        self.add_anchor(AnchorItem("P", QPointF(self.width*191/300, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))
        self.add_anchor(AnchorItem("A", QPointF(self.width*191/300, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))
        self.add_anchor(AnchorItem("B", QPointF(self.width*256/300, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))
        self.add_anchor(AnchorItem("R", QPointF(self.width*256/300, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))
