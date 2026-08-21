"""Base class for graphics nodes that place a linked far-end node (and
the connection between them) the first time they're added to a scene
interactively.

Replaces ExpandableItem's old "grow N anchors via a menu" model -- a
component like Ground/VoltageSource/PressureLine is always exactly two
single-anchor NodeItems joined by an ordinary ConnectionItem. Extra taps
on that connection are junctions (see JunctionNodeItem, split_connection_at
in graphics/view.py) -- nothing here manages more than one anchor per
side, and nothing here handles taps.

See docs/superpowers/specs/2026-08-21-expandable-items-junction-redesign-design.md.
"""

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem

from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.node_item import NodeItem


class PairedTerminalItem(NodeItem):
    # Initial horizontal distance between this node's anchor and its far
    # end's anchor. Purely a placement default -- once spawned, each side
    # is a free-standing NodeItem, draggable independently.
    PAIR_OFFSET_X: float = 120.0

    def setup(self) -> None:
        self._pair_spawned = False
        self.initialize_own_anchor()

    def initialize_own_anchor(self) -> None:
        """Build this node's single anchor (and self.pixmap/width/height).

        Must call self.add_anchor(...) exactly once. Overridden by
        subclasses -- see Ground/VoltageSource/PressureLine.
        """
        raise NotImplementedError

    def create_far_end(self) -> NodeItem:
        """Return the unparented, not-yet-added NodeItem for the other
        end of the pair. Must have exactly one anchor. Overridden by
        subclasses.
        """
        raise NotImplementedError

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged:
            self._maybe_spawn_pair()
        return result

    def _maybe_spawn_pair(self) -> None:
        if self._pair_spawned or self.is_preview or self._loading:
            return
        scene = self.scene()
        if scene is None:
            return
        self._pair_spawned = True

        own_anchor = next(iter(self.anchors.values()))
        far = self.create_far_end()
        far.editor = self.editor
        far_anchor = next(iter(far.anchors.values()))

        # far hasn't been added to a scene yet -- as a top-level item,
        # far.pos() IS its future scenePos, so this places far_anchor
        # PAIR_OFFSET_X to the right of own_anchor, same pattern used by
        # split_connection_at's junction.setPos(point).
        far.setPos(
            own_anchor.scenePos()
            + QPointF(self.PAIR_OFFSET_X, 0)
            - far_anchor.pos()
        )
        scene.addItem(far)

        conn = ConnectionItem(self, own_anchor, far, far_anchor)
        conn.editor = self.editor
        scene.addItem(conn)
        self.connections.append(conn)
        far.connections.append(conn)
        own_anchor.refresh_junction_dot()
        far_anchor.refresh_junction_dot()
