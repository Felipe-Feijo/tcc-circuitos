from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF
from simulation.nodes.reservoir import Reservoir as ReservoirNode


from graphics.items.base.nodes.node_item import NodeItem
from ....anchors.anchor import AnchorItem


class Reservoir(NodeItem):
    node_type = "reservoir"
    simulation_cls = ReservoirNode
    def setup(self) -> None:
        self.pixmap = QPixmap("resources/nodes/reservoir/reservoir.png")
        self.width  = self.pixmap.width()
        self.height = self.pixmap.height()

        self.add_anchor(AnchorItem("T", QPointF(self.width*0.5, self.height*0.95), node=self, domain=self.domain, exit_directions={"external": ["top"]}, margin=65))