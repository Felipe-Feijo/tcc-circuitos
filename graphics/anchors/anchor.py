"""Anchor graphics item -- visible connection point on diagram nodes."""

from PyQt6.QtWidgets import QGraphicsEllipseItem
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QColor, QPen, QPainterPath

from graphics.labels.label import LabelItem
from editor.mode import EditorMode

# (dark theme, light theme) -- same colors as ConnectionItem._get_pen.
_DOMAIN_COLORS = {
    "pneumatic": (QColor(0, 255, 0), QColor(0, 128, 0)),
    "electric": (QColor(255, 255, 0), QColor(184, 132, 0)),
    "hydraulic": (QColor(0, 255, 255), QColor(0, 137, 123)),
}


class AnchorItem(QGraphicsEllipseItem):
    """Visually represents a NodeItem's connection point.

    In CONNECT mode, shows every anchor the current gesture can connect
    to, colored by domain, and detects cursor hover. For hydraulic anchors, keeps pressure and flow labels
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

        # Escape hatch from the generic "dot only at 3+ connections" rule
        # (see refresh_junction_dot) -- for an anchor that must read as a
        # terminal even with a single connection, e.g. Ground/VoltageSource's
        # far end (a bare JunctionNodeItem with no sprite of its own).
        self.always_visible = False

        if domain == "hydraulic":
            self.pressure: float = 0.0
            self.flow: float = 0.0
            self._init_hydraulic_labels()

        # Initial appearance: invisible until refresh_junction_dot says otherwise
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
        if self._is_connect_target():
            self.node.editor.hover_anchor = self
            self.refresh_junction_dot()

    def hoverLeaveEvent(self, event):
        """Restores appearance and clears hover_anchor when the cursor leaves."""
        if not self.node.editor:
            return

        if self.node.editor.hover_anchor is self:
            self.node.editor.hover_anchor = None

        self.refresh_junction_dot()

    def _is_connect_target(self) -> bool:
        """True if a click here can start or complete the CONNECT gesture.

        Mirrors the rules enforced by GraphicsView._complete_connect_press:
        same domain as the source, on a different node.
        """
        editor = getattr(self.node, "editor", None)
        if not editor or editor.mode != EditorMode.CONNECT:
            return False
        source = editor._conn_source_anchor
        return source is None or (
            source.domain == self.domain and source.node is not self.node
        )

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
        """Derives the anchor's appearance from the editor state.

        Called when a connection is created/removed on this anchor, on
        theme changes, and for every anchor on CONNECT mode/gesture
        changes (GraphicsView.refresh_anchors).

        A dot marking a real junction (3+ connections, or always_visible)
        is part of the drawn circuit, so it stays when the anchor is not a
        connect target.
        """
        editor = getattr(self.node, "editor", None)
        in_connect = bool(editor) and editor.mode == EditorMode.CONNECT
        is_source = in_connect and editor._conn_source_anchor is self
        is_target = self._is_connect_target()

        # Qt delivers hover only to the topmost accepting item, so a hidden
        # anchor would otherwise block a connectable one beneath it.
        self.setAcceptHoverEvents(not in_connect or is_source or is_target)

        if is_source:
            brush = QColor(Qt.GlobalColor.gray)
        elif is_target and editor.hover_anchor is self:
            brush = QColor(Qt.GlobalColor.red)
        elif is_target:
            brush = self._domain_color()
        elif self.always_visible or self.connection_count() >= 3:
            brush = QColor(Qt.GlobalColor.lightGray)
        else:
            self.setBrush(Qt.GlobalColor.transparent)
            self.setPen(QPen(Qt.PenStyle.NoPen))
            self.update()
            return

        self.setBrush(brush)
        # White on dark, black on light -- same convention as the
        # default connection pen (ConnectionItem._get_pen) -- a white
        # outline was invisible against a light-theme canvas.
        is_light = getattr(self.node, "use_light_theme", False)
        outline = Qt.GlobalColor.black if is_light else Qt.GlobalColor.white
        self.setPen(QPen(outline, 1))
        self.update()

    def _domain_color(self) -> QColor:
        colors = _DOMAIN_COLORS.get(self.domain)
        if colors is None:
            return QColor(Qt.GlobalColor.lightGray)
        return colors[1 if getattr(self.node, "use_light_theme", False) else 0]

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
