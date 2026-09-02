"""Graphics node for the electrical voltage source symbol."""

from PyQt6.QtCore import QPointF, QCoreApplication
from PyQt6.QtGui import QPixmap

from graphics.anchors.anchor import AnchorItem
from graphics.items.base.nodes.junction_node_item import JunctionNodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.items.base.nodes.paired_terminal_item import PairedTerminalItem
from simulation.nodes.voltage_source import VoltageSource as VoltageSourceNode

_SPRITE = "resources/nodes/voltage_source/voltage_source_terminal.png"


class VoltageSource(PairedTerminalItem):
    node_type = "voltage_source"
    simulation_cls = VoltageSourceNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("electric",),
            sprite=_SPRITE,
            name=QCoreApplication.translate("VoltageSource", "Voltage Source"),
        )

    def initialize_own_anchor(self) -> None:
        self.pixmap = QPixmap(_SPRITE)
        self.width = self.pixmap.width()
        self.height = self.pixmap.height()
        self.add_anchor(AnchorItem(
            "X1", QPointF(self.width, self.height * 0.69),
            node=self, domain=self.domain,
            exit_directions={"external": ["left", "bottom", "top", "right"]},
        ))

    def create_far_end(self):
        # No sprite of its own -- force the junction dot on even at 1
        # connection, or the rail would visually end at nothing.
        junction = JunctionNodeItem(domain=self.domain)
        junction.anchors["J"].always_visible = True
        return junction
