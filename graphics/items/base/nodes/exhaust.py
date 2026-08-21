"""Graphics node for the pneumatic exhaust (pressure outlet to atmosphere)."""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF
from simulation.nodes.nodes import Exhaust as ExhaustNode

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from ....anchors.anchor import AnchorItem


class Exhaust(NodeItem):
    node_type = "exhaust"
    simulation_cls = ExhaustNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("pneumatic",),
            sprite="resources/nodes/exhaust/exhaust.png",
            name="Exhaust",
        )

    def setup(self) -> None:
        self.pixmap = QPixmap("resources/nodes/exhaust/exhaust.png")
        self.width  = self.pixmap.width()
        self.height = self.pixmap.height()

        self.add_anchor(AnchorItem(
            "R",
            QPointF(self.width * 0.5, 0),
            node=self,
            domain=self.domain,
            exit_directions={"external": ["top"]},
        ))
