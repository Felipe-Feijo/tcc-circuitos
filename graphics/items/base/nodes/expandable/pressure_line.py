"""Graphics nodes for the pneumatic pressure line: two terminal-sprite
endpoints joined by an ordinary connection (the "rail"). Extra taps are
junctions on that connection, not more anchors -- see
docs/superpowers/specs/2026-08-21-expandable-items-junction-redesign-design.md.

Both endpoints use Junction as their simulation_cls: a dedicated
PressureLine domain node would be pure pass-through, identical to
Junction, so it isn't reintroduced.
"""

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPixmap

from graphics.anchors.anchor import AnchorItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.paired_terminal_item import PairedTerminalItem
from simulation.nodes.nodes import Junction

_SPRITE = "resources/nodes/pressure_line/pressure_line_terminal.png"


class PressureLineTerminal(NodeItem):
    """The right-hand end of a PressureLine. Plain NodeItem on purpose
    (not PairedTerminalItem) -- it must NOT spawn a pair of its own.
    Never placed from the palette directly; PressureLine.create_far_end()
    is the only place that instantiates it."""
    node_type = "pressure_line_terminal"
    simulation_cls = Junction

    def setup(self) -> None:
        self.pixmap = QPixmap(_SPRITE)
        self.width = self.pixmap.width()
        self.height = self.pixmap.height()
        self.add_anchor(AnchorItem(
            "X1", QPointF(self.width / 2, self.height),
            node=self, domain=self.domain,
            exit_directions={"external": ["right", "bottom", "left"]},
        ))


class PressureLine(PairedTerminalItem):
    node_type = "pressure_line"
    simulation_cls = Junction

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("pneumatic",),
            sprite=_SPRITE,
            name="Pressure Line",
        )

    def initialize_own_anchor(self) -> None:
        self.pixmap = QPixmap(_SPRITE)
        self.width = self.pixmap.width()
        self.height = self.pixmap.height()
        self.add_anchor(AnchorItem(
            "X1", QPointF(self.width / 2, self.height),
            node=self, domain=self.domain,
            exit_directions={"external": ["left", "bottom", "right"]},
        ))

    def create_far_end(self):
        return PressureLineTerminal(domain=self.domain)
