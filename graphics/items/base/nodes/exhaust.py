"""Nó gráfico de escape pneumático (saída de pressão para a atmosfera)."""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF
from simulation.nodes.nodes import Exhaust as ExhaustNode

from graphics.items.base.nodes.node_item import NodeItem
from ....anchors.anchor import AnchorItem


class Exhaust(NodeItem):
    node_type = "exhaust"
    simulation_cls = ExhaustNode

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
