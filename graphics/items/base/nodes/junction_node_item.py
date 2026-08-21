"""Junction node: a branch point created by attaching a connection to
the middle of an already-existing one. Nearly invisible -- draws no
body of its own, just hosts the "J" anchor where 3+ connections meet.
The dot itself is drawn by AnchorItem (see
AnchorItem.refresh_junction_dot), not by this node."""

from PyQt6.QtCore import QPointF, QRectF

from simulation.nodes.nodes import Junction
from graphics.items.base.nodes.node_item import NodeItem
from ....anchors.anchor import AnchorItem

_ALL_DIRECTIONS = ["right", "left", "top", "bottom"]


class JunctionNodeItem(NodeItem):
    node_type = "junction"
    simulation_cls = Junction

    # Radius of the click/drag area around the "J" anchor -- with no
    # visible body of its own, it still needs non-null geometry for Qt
    # to accept selection/drag (ItemIsMovable already comes True from
    # NodeItem.__init__, but has no effect at all without a hit test).
    _HIT_RADIUS = 10

    def setup(self) -> None:
        self.width = 0.0
        self.height = 0.0
        self.add_anchor(AnchorItem(
            "J",
            QPointF(0, 0),
            node=self,
            domain=self.domain,
            exit_directions={
                "external": list(_ALL_DIRECTIONS),
                "internal": list(_ALL_DIRECTIONS),
            },
        ))

    def boundingRect(self) -> QRectF:
        """Centered on the local origin (where the "J" anchor sits), not
        on the corner like NodeItem.boundingRect() (QRectF(0,0,width,height))
        would do -- this way node.pos() stays exactly at the anchor's
        position, requiring no change to split_connection_at's
        setPos(point)."""
        r = self._HIT_RADIUS
        return QRectF(-r, -r, 2 * r, 2 * r)
