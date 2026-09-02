"""4/3-way directional valve graphics node, closed center."""

from PyQt6.QtCore import QPointF, QCoreApplication
from simulation.nodes.directional_valve.valve_4_3_ways import Valve_4_3_Ways as Valve_4_3_WaysNode

from graphics.items.base.nodes.directional_valve.directional_valve_item import DirectionalValveItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from .....anchors.anchor import AnchorItem


class Valve_4_3_Ways(DirectionalValveItem):
    node_type = "valve_4_3_ways"
    simulation_cls = Valve_4_3_WaysNode
    THREE_POSITION = True

    BODY_VISUALS = {
        # Offsets measured relative to the center (state 1), which is the
        # reference (offset 0) -- not relative to state 0, like the
        # 2-position valves.
        0: {  # active-right
            "sprite": "resources/nodes/valve_4_3_ways/valve_4_3_body_right.png",
            "offset": QPointF(-150, 0),
        },
        1: {  # center (rest) -- reference
            "sprite": "resources/nodes/valve_4_3_ways/valve_4_3_body_middle.png",
            "offset": QPointF(0, 0),
        },
        2: {  # active-left
            "sprite": "resources/nodes/valve_4_3_ways/valve_4_3_body_left.png",
            "offset": QPointF(147, 0),
        },
    }

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("pneumatic", "hydraulic"),
            sprite=cls.BODY_VISUALS[1]["sprite"],
            name=QCoreApplication.translate("Valve_4_3_Ways", "Valve 4/3 Ways"),
        )

    def initialize_anchors(self):
        # Constants measured from the sprite's real pixels (450x180) --
        # see docs/superpowers/specs/2026-08-12-valve-4-3-anchor-offset-design.md.
        # The old formula (width*191/300 and width*256/300) was
        # inherited from Valve_4_2_Ways, whose sprite is 300px wide; the
        # 4/3's sprite is 450px, so the anchors landed ~96-129px shifted right.
        self.add_anchor(AnchorItem("P", QPointF(self.width*190/450, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))
        self.add_anchor(AnchorItem("A", QPointF(self.width*190/450, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))
        self.add_anchor(AnchorItem("B", QPointF(self.width*255/450, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))
        self.add_anchor(AnchorItem("R", QPointF(self.width*255/450, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))
