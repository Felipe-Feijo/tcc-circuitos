"""Anchor graphics item -- visible connection point on diagram nodes."""

from PyQt6.QtWidgets import QGraphicsEllipseItem
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPen, QPainterPath

from graphics.labels.label import LabelItem
from editor.mode import EditorMode


class AnchorItem(QGraphicsEllipseItem):
    """Visually represents a NodeItem's connection point.

    Detects cursor hover in CONNECT mode and shows/hides based on
    context. For hydraulic anchors, keeps pressure and flow labels
    updated by ViewSync after each simulation step.

    Args:
        name: The anchor's identifier (e.g. "P", "A", "X1").
        pos: Position relative to the parent node.
        radius: The ellipse's visual radius.
        node: The owning NodeItem.
        domain: The anchor's domain ("pneumatic", "electric" or "hydraulic").
        exit_directions: Exit directions allowed for the A* router.
        margin: Extra margin for the router's collision detection.
    """

    def __init__(self, name: str, pos: QPointF, radius: float = 6,
                 node=None, domain=None, exit_directions=None, margin=None):
        super().__init__(-radius, -radius, 2 * radius, 2 * radius, node)

        self.name = name
        self.id = (node.id, name)
        self.node = node
        self.domain = domain
        self.hit_radius = radius * 4

        # Exit directions for the A* router (e.g. {"external": ["left", "right"]})
        self.exit_directions = exit_directions
        self.margin = margin

        self.setPos(pos)
        self._active = False

        if domain == "hydraulic":
            self.pressure: float = 0.0
            self.flow: float = 0.0
            self._init_hydraulic_labels()

        # Initial appearance: invisible until hover or simulation
        self.setBrush(Qt.GlobalColor.transparent)
        self.setPen(QPen(Qt.PenStyle.NoPen))

        self.setZValue(100)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def shape(self) -> QPainterPath:
        """Returns an expanded hit-detection area to make clicking easier."""
        path = QPainterPath()
        r = self.hit_radius
        path.addEllipse(-r, -r, 2 * r, 2 * r)
        return path

    def boundingRect(self):
        r = self.hit_radius
        return QRectF(-r, -r, 2 * r, 2 * r)

    def hoverEnterEvent(self, event):
        """Highlights the anchor when the cursor enters it in CONNECT mode."""
        if not self.node.editor:
            return

        is_source_anchor = (
            self.node.editor._connecting
            and self.node.editor._conn_source_anchor is self
        )

        if self.node.editor.mode == EditorMode.CONNECT and not is_source_anchor:
            source = self.node.editor._conn_source_anchor

            # Prevents connecting anchors from different domains
            if source and source.domain != self.domain:
                return

            self.setBrush(Qt.GlobalColor.red)
            self.node.editor.hover_anchor = self
            self.update()

    def hoverLeaveEvent(self, event):
        """Restores appearance and clears hover_anchor when the cursor leaves."""
        if not self.node.editor:
            return

        if self.node.editor.hover_anchor is self:
            self.node.editor.hover_anchor = None

        is_source_anchor = (
            self.node.editor._connecting
            and self.node.editor._conn_source_anchor is self
        )

        if not is_source_anchor:
            self.refresh_junction_dot()

    def set_exit_directions(self, directions) -> None:
        """Sets the exit directions allowed for the A* router.

        Args:
            directions: A value accepted by exit_directions (e.g. dict or list).
        """
        self.exit_directions = directions

    def connection_count(self) -> int:
        """How many live ConnectionItems have this anchor as an endpoint
        -- counts only this specific anchor's, not all of the node's (a
        multi-anchor node shouldn't get a dot on an anchor with just 1
        connection because one of its other anchors has 3)."""
        node = self.node
        if not node:
            return 0
        return sum(
            1 for c in getattr(node, "connections", [])
            if c.source_anchor is self or c.target_anchor is self
        )

    def refresh_junction_dot(self) -> None:
        """Shows a permanent dot when this anchor becomes a real junction
        (3+ connections) -- a hydraulic/pneumatic T-fitting or a 3+-
        conductor electric node. Called whenever a connection is
        created/removed on this anchor (GraphicsView.create_connection,
        GraphicsView.split_connection_at, ConnectionItem.prepare_delete)."""
        if self.connection_count() >= 3:
            self.setBrush(Qt.GlobalColor.lightGray)
            self.setPen(QPen(Qt.GlobalColor.white, 1))
        else:
            self.setBrush(Qt.GlobalColor.transparent)
            self.setPen(QPen(Qt.PenStyle.NoPen))
        self.update()

    def reposition_hydraulic_label(self) -> None:
        """Recomputes and applies the hydraulic label's offset.

        Called by NodeItem.rotate() after each rotation, to keep the
        label growing toward the correct outward side (see
        _default_label_offset).
        """
        if hasattr(self, "_label_hydraulic"):
            self._label_hydraulic.setPos(self._default_label_offset())

    def set_hydraulic_labels_visible(self, visible: bool):
        """Shows or hides the hydraulic labels."""
        if hasattr(self, "_label_hydraulic"):
            self._label_hydraulic.setVisible(visible)

    def _init_hydraulic_labels(self):
        """Creates the pressure and flow labels for hydraulic anchors."""
        self._label_hydraulic = LabelItem(properties={
            "text": "0.0 Pa | 0.0 m³/s",
            "editable": False,
            "movable": True,
            "border": False,
            "font_delta": -1,
        })
        self._label_hydraulic.setParentItem(self)
        # If the anchor is born after the node has already rotated (e.g.
        # a pilot anchor Z added at runtime), the label needs the
        # correct counter-rotation right away, not only the next time
        # the node rotates.
        self._label_hydraulic.setRotation(-self.node.rotation())
        self._label_hydraulic.setPos(self._default_label_offset())

    def _default_label_offset(self) -> QPointF:
        """Computes an offset that pushes the label out and away from the component.

        Classifies the edge (top/bottom/left/right) in SCENE coordinates
        -- not local -- because the label is the anchor's child (which
        rotates along with the node) but has ItemIgnoresTransformations
        (see LabelItem): its ORIENTATION always stays upright, but its
        POSITION is still mapped through the inherited transform. If the
        edge were classified in local (pre-rotation) coordinates, the
        offset would always grow in the same "factory" direction even
        after the component rotates -- making the label grow on the
        wrong side (overlapping the sprite) as soon as the node is
        rotated.

        Reusable at any time (not just when the anchor is created) --
        NodeItem.rotate() calls it again after each rotation, to keep
        the label on the correct outward side.
        """
        margin = 4
        rect = self._label_hydraulic.boundingRect()
        w, h = rect.width(), rect.height()

        node = self.node
        anchor_scene_pos = self.scenePos()
        node_scene_rect = node.sceneBoundingRect()

        on_top    = anchor_scene_pos.y() <= node_scene_rect.top() + 1
        on_bottom = anchor_scene_pos.y() >= node_scene_rect.bottom() - 1
        on_left   = anchor_scene_pos.x() <= node_scene_rect.left() + 1
        on_right  = anchor_scene_pos.x() >= node_scene_rect.right() - 1

        if on_top:
            scene_offset = QPointF(-w / 2, -h - margin)
        elif on_bottom:
            scene_offset = QPointF(-w / 2, margin)
        elif on_left:
            scene_offset = QPointF(-w - margin, -h / 2)
        elif on_right:
            scene_offset = QPointF(margin, -h / 2)
        else:
            # Interior anchor (not on any edge): keeps the old default.
            scene_offset = QPointF(margin, -h - margin)

        # scene_offset is in scene coordinates (already upright);
        # converts to the anchor's LOCAL coordinate, which is what
        # setPos() expects -- Qt will remap it back to the scene by
        # applying the rotation again, canceling out this conversion and
        # leaving the label exactly where we computed.
        return self.mapFromScene(anchor_scene_pos + scene_offset)

    def update_hydraulic_labels(self):
        """Updates the pressure and flow labels' text with the current values."""
        if not hasattr(self, "_label_hydraulic"):
            return

        if isinstance(self.pressure, str) or isinstance(self.flow, str):
            self._label_hydraulic.set_text("ERR | ERR")
            return

        p = self.format_hydraulic_value(self.pressure, "Pa")
        q = self.format_hydraulic_value(abs(self.flow), "m³/s")
        self._label_hydraulic.set_text(f"{p} | {q}")

    def format_hydraulic_value(self, value: float, unit: str) -> str:
        if abs(value) < 1e-10:
            return f"0 {unit}"
        if unit == "Pa" and abs(value) < 1.0:
            return f"0 {unit}"
        return f"{value:.3g} {unit}"
