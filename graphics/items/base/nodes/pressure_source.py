"""Nó gráfico de fonte de pressão pneumática."""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF
from simulation.nodes.nodes import PressureSource as PressureSourceNode


from graphics.items.base.nodes.node_item import NodeItem
from ....anchors.anchor import AnchorItem


class PressureSource(NodeItem):
    node_type = "pressure_source"
    simulation_cls = PressureSourceNode
    def setup(self) -> None:
        self.pixmap = QPixmap("resources/nodes/pressure_source/pressure_source.png")
        self.width  = self.pixmap.width()
        self.height = self.pixmap.height()

        self.add_anchor(AnchorItem("P", QPointF(self.width*0.467, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))