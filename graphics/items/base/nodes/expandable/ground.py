"""Graphics node for the electrical ground reference symbol."""

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPixmap

from graphics.anchors.anchor import AnchorItem
from graphics.items.base.nodes.junction_node_item import JunctionNodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.items.base.nodes.paired_terminal_item import PairedTerminalItem
from simulation.nodes.ground import Ground as GroundNode

_SPRITE = "resources/nodes/ground/ground_terminal.png"


class Ground(PairedTerminalItem):
    node_type = "ground"
    simulation_cls = GroundNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("electric",),
            sprite=_SPRITE,
            name="Ground",
        )

    def initialize_own_anchor(self) -> None:
        self.pixmap = QPixmap(_SPRITE)
        self.width = self.pixmap.width()
        self.height = self.pixmap.height()
        self.add_anchor(AnchorItem(
            "X1", QPointF(self.width / 2, 0),
            node=self, domain=self.domain,
            exit_directions={"external": ["left", "right", "top"]},
        ))

    def create_far_end(self):
        # No sprite of its own -- force the junction dot on even at 1
        # connection, or the rail would visually end at nothing.
        junction = JunctionNodeItem(domain=self.domain)
        junction.anchors["J"].always_visible = True
        return junction
