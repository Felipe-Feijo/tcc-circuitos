"""Graphics item for a connection between two diagram anchors."""

from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene, QMenu
from PyQt6.QtGui import QColor, QPainterPath, QPen, QPainter, QPainterPathStroker, QPolygonF, QBrush, QAction
from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer
from graphics.items.base.diagram_item_base import DiagramItemBase
from editor.mode import EditorMode
from graphics.items.base.nodes.junction_node_item import JunctionNodeItem

# Unit vectors per direction -- shared between _apply_margin and _draw_arrow_at.
_DIR_VEC = {"right": (1, 0), "left": (-1, 0), "bottom": (0, 1), "top": (0, -1)}


class ConnectionItem(DiagramItemBase):
    def __init__(self, source_node, source_anchor, target_node=None, target_anchor=None):
        DiagramItemBase.__init__(self)

        self.state: float = 0.0
        self.id = frozenset([source_anchor.id, target_anchor.id if target_anchor else None])

        self.source        = source_node
        self.source_anchor = source_anchor
        self.target        = target_node
        self.target_anchor = target_anchor

        self.temp_target_pos = None
        self._being_deleted  = False

        self.waypoints:              list[QPointF] = []
        self._waypoints_initialized: bool         = False
        self._hovered_wp:            int | None   = None
        self._drag_mode                           = None   # 'waypoint' | 'segment'
        self._drag_wp_index:         int | None   = None
        self._drag_is_horizontal:    bool         = True
        self._drag_original_wps:     list         = []
        self._drag_press_pos:        QPointF | None = None
        self._last_exit_dir:         str          = "right"
        self._last_entry_dir:        str          = "left"
        self._selected_wp:           int | None   = None
        self._last_p1_out:           QPointF | None = None
        self._last_p2_in:            QPointF | None = None

        self.setPos(0, 0)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.use_light_theme: bool = False
        self.pen = QPen(Qt.GlobalColor.cyan if self.domain == "hydraulic" else Qt.GlobalColor.white, 3)
        self.setZValue(-10)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.update()

    @property
    def domain(self):
        return getattr(self.source_anchor, "domain")

    # =========================================================================
    # Qt geometry
    # =========================================================================

    def shape(self) -> QPainterPath:
        points = self.get_path_points()
        if len(points) < 2:
            return QPainterPath()
        line_path = QPainterPath()
        line_path.moveTo(points[0])
        for pt in points[1:]:
            line_path.lineTo(pt)
        stroker = QPainterPathStroker()
        stroker.setWidth(20)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(line_path)

    def boundingRect(self) -> QRectF:
        points = self.get_path_points()
        if len(points) < 2:
            return QRectF()
        margin = 10
        xs = [p.x() for p in points]
        ys = [p.y() for p in points]
        return QRectF(min(xs) - margin, min(ys) - margin,
                      max(xs) - min(xs) + 2 * margin, max(ys) - min(ys) + 2 * margin)

    # =========================================================================
    # Paint
    # =========================================================================

    _ACTIVE_WIDTH   = 5
    _INACTIVE_WIDTH = 3
    _OUTLINE_WIDTH  = 8     # slightly larger than _ACTIVE_WIDTH -- leaves a thin outline
    _OUTLINE_ALPHA  = 140

    def _is_active(self) -> bool:
        """Whether the connection is currently carrying flow/signal --
        same condition `_get_pen` already uses to pick each domain's
        "active" color."""
        if self.domain == "pneumatic":
            return self.state == 1
        if self.domain == "electric":
            return self.state == 1
        if self.domain == "hydraulic":
            return self.state not in (0, "ERR", "PRESSURIZING")
        return False

    def paint(self, painter: QPainter, option, widget=None):
        points = self.get_path_points()
        if len(points) < 2:
            return
        is_preview = self.target_anchor is None
        pen = self._get_pen(is_preview)
        if not is_preview and self._is_active():
            self._draw_outline(painter, points, pen)
        painter.setPen(pen)
        for start, end in zip(points, points[1:]):
            painter.drawLine(start, end)
        if self.waypoints:
            self._draw_waypoint_handles(painter)
        if not is_preview and self.domain == "hydraulic" and self.state != "ERR" and not self.isSelected():
            if len(points) >= 3:
                self._draw_flow_arrows(painter, points, pen)

    def _draw_outline(self, painter: QPainter, points: list, pen: QPen):
        """Thin outline behind the main line, same color as the pen, to
        visually reinforce that the connection is active in the
        simulation.

        Drawn as a single QPainterPath (instead of one drawLine per
        segment) so each corner gets only one join -- separate
        RoundCap segments overlap at the joints and, being
        semi-transparent, stack alpha into more opaque blobs right at
        the waypoints.
        """
        outline_color = QColor(pen.color())
        outline_color.setAlpha(self._OUTLINE_ALPHA)
        outline_pen = QPen(outline_color, self._OUTLINE_WIDTH)
        outline_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        path = QPainterPath()
        path.moveTo(points[0])
        for pt in points[1:]:
            path.lineTo(pt)
        painter.setPen(outline_pen)
        painter.drawPath(path)

    def _get_pen(self, is_preview: bool = False) -> QPen:
        if is_preview:
            pen = QPen(QColor(150, 150, 150), 2)
            pen.setStyle(Qt.PenStyle.DashLine)
            return pen
        width = self._ACTIVE_WIDTH if self._is_active() else self._INACTIVE_WIDTH
        if self.isSelected():
            return QPen(Qt.GlobalColor.blue, 3)
        if self.domain == "pneumatic" and self.state == 1:
            return QPen(Qt.GlobalColor.green, width)
        if self.domain == "electric" and self.state == 1:
            return QPen(Qt.GlobalColor.yellow, width)
        if self.domain == "hydraulic":
            if self.state == "ERR":          return QPen(Qt.GlobalColor.red, 3)
            if self.state == "PRESSURIZING": return QPen(QColor(255, 140, 0), 3)
            if self.state > 0:               return QPen(Qt.GlobalColor.blue, width)
            if self.state < 0:               return QPen(QColor(100, 180, 255), width)
            return QPen(Qt.GlobalColor.cyan, 3)
        # Default pen — white on dark theme, black on light theme.
        if self.domain != "hydraulic":
            color = Qt.GlobalColor.black if self.use_light_theme else Qt.GlobalColor.white
            return QPen(color, 3)
        return self.pen

    def _draw_flow_arrows(self, painter: QPainter, points: list, pen: QPen):
        arrow_offset = 6
        flow_a = getattr(self.source_anchor, "flow", 0.0)
        if not isinstance(flow_a, str) and abs(flow_a) > 1e-10:
            exit_dir = self._get_exit_direction()
            self._draw_arrow_at(painter, self._apply_margin(points[1], exit_dir, -arrow_offset), exit_dir, flow_a, pen)
        if self.target_anchor:
            flow_b = getattr(self.target_anchor, "flow", 0.0)
            if not isinstance(flow_b, str) and abs(flow_b) > 1e-10:
                is_internal = self.source_anchor.node == self.target_anchor.node
                exit_key    = "internal" if is_internal else "external"
                entry_dirs  = self.target_anchor.exit_directions.get(exit_key, ["left"])
                entry_dir   = self._choose_best_exit_direction(points[-1], points[0], entry_dirs)
                self._draw_arrow_at(painter, self._apply_margin(points[-2], entry_dir, -arrow_offset), entry_dir, flow_b, pen)

    def _draw_arrow_at(self, painter: QPainter, point: QPointF, direction: str, flow: float, pen: QPen):
        size = 10
        ux, uy = _DIR_VEC.get(direction, (1, 0))
        if flow > 0:
            ux, uy = -ux, -uy
        tip   = QPointF(point.x() + ux * size,      point.y() + uy * size)
        base  = QPointF(point.x() - ux * size,      point.y() - uy * size)
        left  = QPointF(base.x() - uy * size * 0.6, base.y() + ux * size * 0.6)
        right = QPointF(base.x() + uy * size * 0.6, base.y() - ux * size * 0.6)
        # Black in light theme, white in dark -- guaranteed contrast
        # against any hydraulic state color (blue, cyan, orange...),
        # independent of the line's own color.
        arrow_color = Qt.GlobalColor.black if self.use_light_theme else Qt.GlobalColor.white
        painter.setBrush(QBrush(arrow_color))
        painter.setPen(QPen(arrow_color, 1))
        painter.drawPolygon(QPolygonF([tip, left, right]))

    # =========================================================================
    # Path computation
    # =========================================================================

    def get_path_points(self):
        if getattr(self, "_being_deleted", False):
            return []
        source_anchor = getattr(self, "source_anchor", None)
        target_anchor = getattr(self, "target_anchor", None)
        if not source_anchor or not source_anchor.scene():
            return []

        p1 = source_anchor.scenePos()

        if target_anchor and target_anchor.scene():
            p2, is_preview = target_anchor.scenePos(), False
        elif self.temp_target_pos:
            p2, is_preview = self.temp_target_pos, True
        else:
            return [p1]

        is_internal  = target_anchor and source_anchor.node == target_anchor.node
        exit_key     = "internal" if is_internal else "external"
        source_dirs  = source_anchor.exit_directions.get(exit_key, ["right"])
        exit_dir     = self._choose_best_exit_direction(p1, p2, source_dirs)
        source_margin, target_margin = self._compute_margins(p1, p2)
        p1_out       = self._apply_margin(p1, exit_dir, source_margin)

        if is_preview:
            dx, dy = abs(p2.x() - p1_out.x()), abs(p2.y() - p1_out.y())
            middle = self._hvh(p1_out, p2) if dx > dy else self._vhv(p1_out, p2)
            return [p1, p1_out, *middle, p2]

        target_dirs = target_anchor.exit_directions.get(exit_key, ["left"])
        # entry_dir is always derived from the anchor's real exit_directions --
        # never inferred from the vector to the waypoint, since that fails with
        # corrupted waypoints or A*'s different margin (EXIT_PX=40px vs the editor's 6-18px).
        entry_dir   = self._choose_best_exit_direction(p2, p1, target_dirs)
        p2_in       = self._apply_margin(p2, entry_dir, target_margin)

        if not self._waypoints_initialized:
            self._waypoints_initialized = True
            self.waypoints = [QPointF(pt) for pt in
                              self._route_between_points(p1_out, p2_in, exit_dir, entry_dir)]
            self._last_p1_out = QPointF(p1_out)
            self._last_p2_in  = QPointF(p2_in)

        self._last_exit_dir  = exit_dir
        self._last_entry_dir = entry_dir
        return [p1, p1_out, *self.waypoints, p2_in, p2]

    def _compute_margins(self, p1: QPointF, p2: QPointF):
        dist     = abs(p2.x() - p1.x()) + abs(p2.y() - p1.y())
        adaptive = min(18, max(6, dist * 0.15))
        return (getattr(self.source_anchor, "margin", None) or adaptive,
                getattr(self.target_anchor, "margin", None) or adaptive if self.target_anchor else adaptive)

    def _choose_best_exit_direction(self, from_point: QPointF, to_point: QPointF, allowed_dirs: list) -> str:
        if len(allowed_dirs) == 1:
            return allowed_dirs[0]
        dx, dy = to_point.x() - from_point.x(), to_point.y() - from_point.y()
        score = {"right":  abs(dx) if dx > 0 else -1000,
                 "left":   abs(dx) if dx < 0 else -1000,
                 "bottom": abs(dy) if dy > 0 else -1000,
                 "top":    abs(dy) if dy < 0 else -1000}
        return max(allowed_dirs, key=lambda d: score.get(d, -1000))

    def _apply_margin(self, point: QPointF, direction: str, margin: float) -> QPointF:
        ux, uy = _DIR_VEC[direction]
        return QPointF(point.x() + ux * margin, point.y() + uy * margin)

    def _get_exit_direction(self) -> str:
        """Exit direction of the source anchor toward the target."""
        _, _, _, _, exit_dir, _ = self._compute_exit_entry()
        return exit_dir

    def _compute_exit_entry(self):
        """Returns (p1, p2, p1_out, p2_in, exit_dir, entry_dir) for the current anchors."""
        p1, p2 = self.source_anchor.scenePos(), self.target_anchor.scenePos()
        is_internal = self.source_anchor.node == self.target_anchor.node
        exit_key    = "internal" if is_internal else "external"
        source_dirs = self.source_anchor.exit_directions.get(exit_key, ["right"])
        target_dirs = self.target_anchor.exit_directions.get(exit_key, ["left"])
        exit_dir    = self._choose_best_exit_direction(p1, p2, source_dirs)
        entry_dir   = self._choose_best_exit_direction(p2, p1, target_dirs)
        source_margin, target_margin = self._compute_margins(p1, p2)
        return p1, p2, self._apply_margin(p1, exit_dir, source_margin), \
               self._apply_margin(p2, entry_dir, target_margin), exit_dir, entry_dir

    def _resolved_points(self, wps: list | None = None) -> tuple[list, frozenset]:
        """Full point sequence for neighbor/collinearity calculations,
        including the anchor's margin points as 'anchored' entries.

        Anchored = always recomputed from the anchor's current position
        (so it tracks the component on move, for free); never a direct
        drag target nor shown as a handle; never deletable. Single
        source of truth for "who is whose neighbor" -- used by both
        waypoint dragging and boundary repair after moving a node.

        `wps` lets this be computed against an explicit waypoint list
        (e.g. a snapshot frozen during a drag) instead of
        `self.waypoints`.
        """
        if not self.target_anchor:
            return [], frozenset()
        _, _, p1_out, p2_in, _, _ = self._compute_exit_entry()
        points = [p1_out, *(self.waypoints if wps is None else wps), p2_in]
        return points, frozenset({0, len(points) - 1})

    # =========================================================================
    # Routing helpers
    # =========================================================================

    def _route_between_points(self, p1_out: QPointF, p2_in: QPointF, exit_dir: str, entry_dir: str) -> list:
        dx, dy     = p2_in.x() - p1_out.x(), p2_in.y() - p1_out.y()
        is_exit_h  = exit_dir  in ("left", "right")
        is_entry_h = entry_dir in ("left", "right")
        exit_conflict_h  = (exit_dir  == "left"   and dx > 0) or (exit_dir  == "right"  and dx < 0)
        exit_conflict_v  = (exit_dir  == "top"    and dy > 0) or (exit_dir  == "bottom" and dy < 0)
        entry_conflict_h = (entry_dir == "left"   and dx < 0) or (entry_dir == "right"  and dx > 0)
        entry_conflict_v = (entry_dir == "top"    and dy < 0) or (entry_dir == "bottom" and dy > 0)

        def four_seg(p1, p2):
            # Chooses hvhv or vhvh depending on the relative quadrant.
            return (self._hvhv if (dy > 0 or (dy == 0 and dx > 0)) else self._vhvh)(p1, p2)

        if is_exit_h:
            if exit_conflict_h:
                return four_seg(p1_out, p2_in) if entry_conflict_v else self._vhv(p1_out, p2_in)
            if is_entry_h:
                return four_seg(p1_out, p2_in) if entry_conflict_h else self._hvh(p1_out, p2_in)
            return self._hvh(p1_out, p2_in)
        else:
            if exit_conflict_v:
                return four_seg(p1_out, p2_in) if entry_conflict_h else self._hvh(p1_out, p2_in)
            if not is_entry_h:
                return four_seg(p1_out, p2_in) if entry_conflict_v else self._vhv(p1_out, p2_in)
            return self._vhv(p1_out, p2_in)

    # Orthogonal routing primitives (names = sequence of H/V segments).
    def _vhv(self, p1, p2):
        if p1.x() == p2.x():
            return []  # already aligned on the x axis -- straight line, no degenerate "V"
        mid_y = (p1.y() + p2.y()) / 2
        return [QPointF(p1.x(), mid_y), QPointF(p2.x(), mid_y)]

    def _hvh(self, p1, p2):
        if p1.y() == p2.y():
            return []  # already aligned on the y axis -- straight line, no degenerate "V"
        mid_x = (p1.x() + p2.x()) / 2
        return [QPointF(mid_x, p1.y()), QPointF(mid_x, p2.y())]

    def _hvhv(self, p1, p2):
        mid_x, mid_y = (p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2
        return [QPointF(mid_x, p1.y()), QPointF(mid_x, mid_y), QPointF(p2.x(), mid_y)]

    def _vhvh(self, p1, p2):
        mid_x, mid_y = (p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2
        return [QPointF(p1.x(), mid_y), QPointF(mid_x, mid_y), QPointF(mid_x, p2.y())]

    def update_temp_endpoint(self, scene_pos: QPointF):
        self.prepareGeometryChange()
        self.temp_target_pos = scene_pos
        self.update()

    def update_position(self):
        if not getattr(self, '_being_deleted', False):
            self.prepareGeometryChange()
            self.update()

    def _anchors_in_scene(self) -> bool:
        return (bool(self.source_anchor and self.target_anchor) and
                bool(self.source_anchor.scene() and self.target_anchor.scene()))

    def adjust_waypoints_for_node_move(self, moved_source: bool = True, moved_target: bool = True) -> None:
        """Realigns the boundary segment on the side that moved.

        Delegates to `_adjust_boundary()`, which distinguishes a
        redundant loose point (should follow the boundary) from a
        deliberate user corner that only coincidentally shares an axis
        with the boundary (should become a new bridge, leaving the rest
        of the detour untouched) -- see `_adjust_boundary` for the
        algorithm's details.

        Special case: when ALL waypoints are collinear with each other
        on the axis shared by exit_dir/entry_dir (both H or both V -- a
        single waypoint sharing both boundaries is the most common case,
        but a deliberate 2+ waypoint bend on that same axis falls into
        the same trap), the two shifts below both claim the entire
        array and the second one fully overwrites the first, collapsing
        the bend into a single diagonal segment (found via live-UI
        testing with a horizontal-vertical-horizontal Z between two
        anchors exiting vertically -- the 2 middle waypoints, collinear
        in x, were "swallowed" by the source side and then the target
        side). No combination of individual shifts fixes this; reroutes
        this segment instead, same as we already did for n==1.
        """
        if getattr(self, '_being_deleted', False) or not self._waypoints_initialized:
            return
        if not self._anchors_in_scene():
            return

        _, _, p1_out, p2_in, exit_dir, entry_dir = self._compute_exit_entry()
        exit_h, entry_h = exit_dir in ("left", "right"), entry_dir in ("left", "right")
        wps = self.waypoints
        n   = len(wps)

        # Straight route (no waypoints at all) -- the most common case
        # of all (any split made right on a straight line starts this
        # way). _adjust_boundary() below has nothing to adjust here (no
        # `w` to touch), so this segment was completely unprotected: if
        # the side that moved has a free-direction anchor (a
        # JunctionNodeItem's "J" accepts all 4), the p1_out->p2_in
        # segment stops sharing an axis and becomes a straight diagonal
        # -- reproduced by a real user report, easy to trigger by
        # dragging a freshly-created junction from a straight split.
        # Reroutes from scratch in this case -- nothing to preserve in a
        # waypoint-less segment.
        if n == 0:
            if moved_source or moved_target:
                same_axis = (abs(p1_out.x() - p2_in.x()) < 0.5
                             or abs(p1_out.y() - p2_in.y()) < 0.5)
                if not same_axis:
                    self._reroute_waypoints()
            return

        # Still-"pristine" route: if the current waypoints match exactly
        # what `_route_between_points` would generate from the anchors'
        # last validated position (`_last_p1_out`/`_last_p2_in` + cached
        # directions), then nobody ever dragged/inserted/edited anything
        # here -- it's a purely automatic route (hvh/vhv/hvhv/vhvh).
        # `_adjust_boundary` has no way to know this: its only signal is
        # "`w` was aligned with the anchor" (`was_aligned`), which is
        # false by construction for a hvhv/vhvh's intermediate offset
        # point (it sits mid-path, never on top of the anchor) --
        # without this check, an automatic 3-point route would gain a
        # spurious bridge on move, instead of simply rerouting (which is
        # always safe here, since there's no manual detour to
        # preserve).
        if ((moved_source or moved_target) and wps and
                self._last_p1_out is not None and self._last_p2_in is not None):
            pristine = self._route_between_points(self._last_p1_out, self._last_p2_in,
                                                    self._last_exit_dir, self._last_entry_dir)
            if len(pristine) == len(wps) and all(
                    abs(a.x() - b.x()) < 0.5 and abs(a.y() - b.y()) < 0.5
                    for a, b in zip(pristine, wps)):
                self._reroute_waypoints()
                return

        if moved_source and moved_target and exit_h == entry_h:
            axis_val = (lambda p: p.x()) if not exit_h else (lambda p: p.y())
            ref = axis_val(wps[0])
            if all(abs(axis_val(p) - ref) < 0.5 for p in wps):
                self._reroute_waypoints()
                return

        self.prepareGeometryChange()
        if moved_source:
            self._adjust_boundary(1, p1_out, self._last_p1_out, exit_h)
            self._last_p1_out = QPointF(p1_out)
        if moved_target:
            self._adjust_boundary(-1, p2_in, self._last_p2_in, entry_h)
            self._last_p2_in = QPointF(p2_in)
        if moved_source or moved_target:
            # Keeps the "pristine" check above valid on subsequent
            # moves: without this, `_last_exit_dir`/`_last_entry_dir`
            # would stay stuck at the direction from before this
            # connection's FIRST move (only `get_path_points()`/
            # `_reroute_waypoints()` updated these two fields).
            self._last_exit_dir  = exit_dir
            self._last_entry_dir = entry_dir
        self.update()

    def _adjust_boundary(self, step: int, anchor_pt: QPointF,
                          old_anchor_pt: 'QPointF | None', is_horizontal: bool) -> None:
        """Realigns the waypoint(s) near the boundary that moved.

        step: +1 for the source side (walks wps[0], wps[1], ...), -1 for
        the target side (walks wps[-1], wps[-2], ...).
        anchor_pt: the anchor's current (post-move) margin point.
        old_anchor_pt: cached anchor position from the last time the
        geometry was validated (None if never validated -- treated as
        "no history", never assumes redundancy).
        is_horizontal: whether the locked axis is Y (True) or X (False).

        Walks from the boundary inward. At each waypoint `w`:
          - No inward neighbor (end of the list): snaps `w` to the
            anchor, stop.
          - `w` doesn't share the locked axis with the inward neighbor
            `w2`: snaps only `w`, stop (no conflict -- the common
            automatic-route case, w2 and the rest stay untouched).
          - `w` shares the locked axis with `w2` AND `w` was already
            aligned with `old_anchor_pt` on that axis (a redundant loose
            point, e.g. inserted by double-clicking a straight line):
            snaps `w`, continues to `w2` using `w`'s OLD position as the
            new reference (the line continues).
          - `w` shares the locked axis with `w2` but was NOT aligned
            with `old_anchor_pt` (a deliberate user corner -- e.g. a
            manual detour that ends on this axis by coincidence):
            doesn't touch `w` or anything after it. Inserts a "bridge"
            waypoint between `w` and the anchor -- locked axis matching
            the anchor, the other axis matching `w` -- exactly what a
            user would do manually to resolve this conflict.
        """
        wps = self.waypoints
        n = len(wps)
        if n == 0:
            return
        idx = 0 if step == 1 else n - 1
        ref_anchor = old_anchor_pt

        def locked(p: QPointF) -> float:
            return p.y() if is_horizontal else p.x()

        def snap(p: QPointF, target: QPointF) -> QPointF:
            return QPointF(p.x(), target.y()) if is_horizontal else QPointF(target.x(), p.y())

        while True:
            w = wps[idx]
            inward_idx = idx + step
            has_inward = 0 <= inward_idx < n

            if not has_inward:
                wps[idx] = snap(w, anchor_pt)
                return

            w2 = wps[inward_idx]
            if abs(locked(w) - locked(w2)) >= 0.5:
                wps[idx] = snap(w, anchor_pt)
                return

            was_aligned = ref_anchor is not None and abs(locked(w) - locked(ref_anchor)) < 0.5
            if was_aligned:
                old_w = QPointF(w)
                wps[idx] = snap(w, anchor_pt)
                ref_anchor = old_w
                idx = inward_idx
                continue

            bridge = snap(QPointF(w), anchor_pt)
            insert_at = idx if step == 1 else idx + 1
            wps.insert(insert_at, bridge)
            return

    # =========================================================================
    # Waypoints — constants
    # =========================================================================

    _WP_HIT_RADIUS    = 10
    _WP_HOVER_RANGE   = 20
    _SEG_HIT_DIST     = 8
    _WP_VISIBLE_RANGE = 40
    _CLICK_EPSILON     = 2.0   # px -- below this, press+release counts as a click, not a drag

    # =========================================================================
    # Waypoints — hit detection
    # =========================================================================

    @staticmethod
    def _dist_point_to_seg(px, py, ax, ay, bx, by) -> float:
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return ((px-ax)**2 + (py-ay)**2) ** 0.5
        t = max(0.0, min(1.0, ((px-ax)*dx + (py-ay)*dy) / (dx*dx+dy*dy)))
        return ((px-ax-t*dx)**2 + (py-ay-t*dy)**2) ** 0.5

    def _wp_index_at(self, scene_pos: QPointF, radius: int | None = None) -> int | None:
        r2 = (radius if radius is not None else self._WP_HIT_RADIUS) ** 2
        best, best_i = r2, None
        for i, wp in enumerate(self.waypoints):
            d2 = (scene_pos.x()-wp.x())**2 + (scene_pos.y()-wp.y())**2
            if d2 < best:
                best, best_i = d2, i
        return best_i

    def _seg_hit_at(self, scene_pos: QPointF):
        pts = self.get_path_points()
        if len(pts) < 2:
            return None
        px, py = scene_pos.x(), scene_pos.y()
        inner  = pts[1:-1]
        best_d, result = self._SEG_HIT_DIST + 1, None
        for i in range(len(inner) - 1):
            a, b = inner[i], inner[i+1]
            d = self._dist_point_to_seg(px, py, a.x(), a.y(), b.x(), b.y())
            if d < best_d:
                best_d, result = d, (i, QPointF(a), QPointF(b))
        return result

    def compute_split_point(self, scene_pos: QPointF):
        """Point closest to `scene_pos` on the routed path (not the
        straight point-to-point line), to create a junction there.

        Returns (point, waypoints_before, waypoints_after) -- the two
        lists already ready to become `self.waypoints` for the two
        ConnectionItems resulting from the split -- or None if
        `scene_pos` is too far from any segment (same radius as
        `_seg_hit_at`, also used by the double-click that inserts a
        waypoint).
        """
        hit = self._seg_hit_at(scene_pos)
        if hit is None:
            return None
        k, seg_a, seg_b = hit
        is_horizontal = abs(seg_a.y() - seg_b.y()) < 1.0
        point = (QPointF(scene_pos.x(), seg_a.y()) if is_horizontal
                 else QPointF(seg_a.x(), scene_pos.y()))
        return point, list(self.waypoints[:k]), list(self.waypoints[k:])

    # =========================================================================
    # Waypoints — drawing
    # =========================================================================

    def _draw_waypoint_handles(self, painter: QPainter):
        if self.editor and self.editor.mode == EditorMode.SIMULATE:
            return
        if self._hovered_wp is None and self._drag_mode is None and self._selected_wp is None:
            return
        r              = self._WP_HIT_RADIUS
        dragging_idx   = self._drag_wp_index if self._drag_mode is not None else None
        hover_wp       = self._hovered_wp
        visible_range2 = self._WP_VISIBLE_RANGE ** 2

        # Reference point for the handles' visibility range.
        ref_pos: QPointF | None = None
        if hover_wp is not None and hover_wp < len(self.waypoints):
            ref_pos = self.waypoints[hover_wp]
        elif dragging_idx is not None and dragging_idx < len(self.waypoints):
            ref_pos = self.waypoints[dragging_idx]
        elif self._selected_wp is not None and self._selected_wp < len(self.waypoints):
            ref_pos = self.waypoints[self._selected_wp]

        for i, wp in enumerate(self.waypoints):
            if ref_pos is not None and (wp.x()-ref_pos.x())**2 + (wp.y()-ref_pos.y())**2 > visible_range2:
                continue
            if self._drag_mode == 'waypoint' and i == dragging_idx:
                fill, border = QColor(220, 40, 40),        QColor(255, 120, 120)
            elif i == self._selected_wp:
                fill, border = QColor(60, 120, 255, 230),  QColor(120, 180, 255, 255)
            elif hover_wp is not None:
                fill, border = QColor(200, 200, 200, 200), QColor(255, 255, 255, 220)
            else:
                continue
            painter.setPen(QPen(border, 1))
            painter.setBrush(fill)
            diamond = QPainterPath()
            diamond.moveTo(wp.x(),     wp.y() - r)
            diamond.lineTo(wp.x() + r, wp.y())
            diamond.lineTo(wp.x(),     wp.y() + r)
            diamond.lineTo(wp.x() - r, wp.y())
            diamond.closeSubpath()
            painter.drawPath(diamond)

    # =========================================================================
    # Waypoints — mutation
    # =========================================================================

    def reanchor_waypoints(self) -> None:
        """Fixes up the route right after building a ConnectionItem whose
        waypoints came from ANOTHER connection (a line split in
        GraphicsView.split_connection_at, or a merge when collapsing a
        junction in _merge_junction_if_collapsed) -- they were captured
        under the source connection's margins/exit direction, which
        aren't necessarily the same ones this new connection computes
        for itself.

        A JunctionNodeItem's "J" anchor accepts all 4 directions (see
        JunctionNodeItem.setup), so the "ideal" direction
        _choose_best_exit_direction picks can differ from the source
        connection's even with no node having moved -- without this
        fix, the first/last segment can come out diagonal right at
        creation (reproduced for real: a user reported lines losing
        orthogonality when creating/moving/deleting junctions).

        No waypoints (straight route): reroutes from scratch -- nothing
        to preserve. With waypoints: reuses
        adjust_waypoints_for_node_move() as if this were the first time
        both sides "moved" -- same snap/bridge logic already used (and
        correct by construction: each `snap()` call only overwrites the
        coordinate of the axis NOT shared with the inward neighbor, so
        an axis that was already shared is never touched) when an
        existing node is dragged.
        """
        if not self._anchors_in_scene():
            return
        if not self.waypoints:
            self._reroute_waypoints()
            return
        self.adjust_waypoints_for_node_move(moved_source=True, moved_target=True)

    def _reroute_waypoints(self):
        """Discards the current waypoints and recomputes the route from scratch."""
        if not self._anchors_in_scene():
            return
        _, _, p1_out, p2_in, exit_dir, entry_dir = self._compute_exit_entry()
        self.waypoints = [QPointF(pt) for pt in
                          self._route_between_points(p1_out, p2_in, exit_dir, entry_dir)]
        self._last_p1_out    = QPointF(p1_out)
        self._last_p2_in     = QPointF(p2_in)
        self._last_exit_dir  = exit_dir
        self._last_entry_dir = entry_dir
        self.prepareGeometryChange()

    def _delete_waypoint(self, idx: int):
        if not (0 <= idx < len(self.waypoints)):
            return
        self.prepareGeometryChange()
        self.waypoints.pop(idx)
        if self._selected_wp == idx:
            self._selected_wp = None
        elif self._selected_wp is not None and self._selected_wp > idx:
            self._selected_wp -= 1
        self._hovered_wp = None
        self._reroute_waypoints()
        self.update()

    def _insert_waypoint_at_segment(self, scene_pos: QPointF):
        """Inserts a waypoint on the nearest segment; returns its index or None."""
        hit = self._seg_hit_at(scene_pos)
        if hit is None:
            return None
        ins_idx, seg_a, seg_b = hit
        is_horizontal = abs(seg_a.y() - seg_b.y()) < 1.0
        wp = QPointF(scene_pos.x(), seg_a.y()) if is_horizontal else QPointF(seg_a.x(), scene_pos.y())
        self.prepareGeometryChange()
        self.waypoints.insert(ins_idx, wp)
        self.update()
        return ins_idx

    def _reset_drag_state(self):
        self._drag_mode          = None
        self._drag_wp_index      = None
        self._drag_is_horizontal = True
        self._drag_original_wps  = []
        self._drag_press_pos     = None

    # =========================================================================
    # Mouse events
    # =========================================================================

    def mousePressEvent(self, event):
        sp = event.scenePos()

        if event.button() == Qt.MouseButton.RightButton:
            idx = self._wp_index_at(sp)
            if idx is not None:
                self._selected_wp = idx
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
                self.setSelected(False)
                self._show_wp_context_menu(idx, event)
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                if self.isSelected():
                    self.setSelected(False)
                self.update()
                event.accept()
                return
            super().mousePressEvent(event)
            return

        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        self._reset_drag_state()

        idx = self._wp_index_at(sp)
        if idx is not None:
            self._selected_wp       = None if self._selected_wp == idx else idx
            self._drag_mode         = 'waypoint'
            self._drag_wp_index     = idx
            self._drag_original_wps = [QPointF(p) for p in self.waypoints]
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self.setSelected(False)
            self.update()
            event.accept()
            return

        if self._selected_wp is not None:
            self._selected_wp = None
            self.update()

        hit = self._seg_hit_at(sp)
        if hit is not None:
            ins_idx, seg_a, seg_b = hit
            self._drag_is_horizontal = abs(seg_a.y() - seg_b.y()) < 1.0
            self._drag_mode          = 'segment'
            self._drag_wp_index      = ins_idx
            self._drag_press_pos     = QPointF(sp)
            self.prepareGeometryChange()
            self.waypoints.insert(ins_idx,     QPointF(seg_a))
            self.waypoints.insert(ins_idx + 1, QPointF(seg_b))
            self.update()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        sp = event.scenePos()

        if self._drag_mode == 'waypoint':
            i = self._drag_wp_index
            if i is not None and 0 <= i < len(self._drag_original_wps):
                orig_wps = self._drag_original_wps
                full, _  = self._resolved_points(orig_wps)
                fi   = i + 1  # shift to the index in `full`, which has p1_out at the front
                orig = full[fi]
                prev_h = abs(full[fi-1].y() - orig.y()) < 0.5
                prev_v = abs(full[fi-1].x() - orig.x()) < 0.5
                next_h = abs(full[fi+1].y() - orig.y()) < 0.5
                next_v = abs(full[fi+1].x() - orig.x()) < 0.5
                # full[0]/full[-1] are the anchor's margin points
                # (p1_out/p2_in), not waypoints -- they never move to
                # follow the drag. So when the neighbor in question IS
                # the anchor (fi-1 == 0 or fi+1 == len(full)-1), a
                # matching axis must LOCK that axis (otherwise the
                # segment to the anchor becomes diagonal, since there's
                # no way to compensate by moving the other side). When
                # the neighbor is a real waypoint, a matching axis FREES
                # movement on that axis, because the write block below
                # drags the neighbor along to keep the segment
                # orthogonal.
                prev_is_anchor = fi - 1 == 0
                next_is_anchor = fi + 1 == len(full) - 1
                lock_y = (prev_h and prev_is_anchor) or (next_h and next_is_anchor)
                lock_x = (prev_v and prev_is_anchor) or (next_v and next_is_anchor)
                free_y = not lock_y and ((prev_h and not prev_is_anchor) or (next_h and not next_is_anchor))
                free_x = not lock_x and ((prev_v and not prev_is_anchor) or (next_v and not next_is_anchor))
                new_x  = sp.x() if free_x else orig.x()
                new_y  = sp.y() if free_y else orig.y()
                wps = [QPointF(p) for p in orig_wps]
                wps[i] = QPointF(new_x, new_y)
                if i > 0:
                    if prev_h:   wps[i-1] = QPointF(wps[i-1].x(), new_y)
                    elif prev_v: wps[i-1] = QPointF(new_x, wps[i-1].y())
                if i < len(wps) - 1:
                    if next_h:   wps[i+1] = QPointF(wps[i+1].x(), new_y)
                    elif next_v: wps[i+1] = QPointF(new_x, wps[i+1].y())
                self.waypoints   = wps
                self._hovered_wp = i
                self.prepareGeometryChange()
                self.update()
            event.accept()
            return

        if self._drag_mode == 'segment':
            i = self._drag_wp_index
            if i is not None and i + 1 < len(self.waypoints):
                wp1, wp2 = self.waypoints[i], self.waypoints[i + 1]
                if self._drag_is_horizontal:
                    self.waypoints[i], self.waypoints[i+1] = QPointF(wp1.x(), sp.y()), QPointF(wp2.x(), sp.y())
                else:
                    self.waypoints[i], self.waypoints[i+1] = QPointF(sp.x(), wp1.y()), QPointF(sp.x(), wp2.y())
                self.prepareGeometryChange()
                self.update()
            event.accept()
            return

        idx = self._wp_index_at(sp)
        if idx != self._hovered_wp:
            self._hovered_wp = idx
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        was_waypoint_drag = (self._drag_mode == 'waypoint')
        if self._drag_mode == 'segment':
            sp     = event.scenePos()
            press  = self._drag_press_pos
            moved  = press is not None and (
                abs(sp.x() - press.x()) >= self._CLICK_EPSILON or
                abs(sp.y() - press.y()) >= self._CLICK_EPSILON
            )
            if moved:
                self._collapse_segment_corners()
            else:
                self._undo_segment_split()
        self._reset_drag_state()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        super().mouseReleaseEvent(event)
        if was_waypoint_drag and self.isSelected():
            self.setSelected(False)

    def _collapse_segment_corners(self):
        """Removes redundant waypoints after a segment drag (3 collinear points)."""
        if not self.waypoints:
            return
        resolved = self._resolved_points()[0]
        p1_out   = resolved[0]  if resolved else None
        p2_in    = resolved[-1] if resolved else None

        def neighbour(i):
            if i < 0:                    return p1_out
            if i >= len(self.waypoints): return p2_in
            return self.waypoints[i]

        changed = True
        while changed and self.waypoints:
            changed = False
            i = 0
            while i < len(self.waypoints):
                prev, curr, nxt = neighbour(i-1), self.waypoints[i], neighbour(i+1)
                if prev is None or nxt is None:
                    i += 1
                    continue
                collinear = ((abs(prev.y()-curr.y()) < 0.5 and abs(curr.y()-nxt.y()) < 0.5) or
                             (abs(prev.x()-curr.x()) < 0.5 and abs(curr.x()-nxt.x()) < 0.5))
                if collinear:
                    self.waypoints.pop(i)
                    changed = True
                else:
                    i += 1
        self.prepareGeometryChange()
        # Doesn't call adjust_waypoints_for_node_move()/_adjust_boundary()
        # here: a segment drag moves the inserted seg_a/seg_b copies
        # together (mousePressEvent/mouseMoveEvent above), preserving
        # boundary orthogonality by construction -- no boundary repair
        # needed.
        self.update()

    def _undo_segment_split(self):
        """Undoes the temporary segment split when the press+release had
        no real movement -- i.e. it was a selection click, not a drag.
        Just removes the 2 waypoints inserted in mousePressEvent: this
        never goes through adjust_waypoints_for_node_move, so a
        connection with a non-trivial route (e.g. from a generator)
        isn't at risk of being replaced by the default heuristic routing
        just from being clicked.
        """
        i = self._drag_wp_index
        if i is not None and 0 <= i + 1 < len(self.waypoints):
            self.prepareGeometryChange()
            self.waypoints.pop(i + 1)
            self.waypoints.pop(i)
            self.update()

    def mouseDoubleClickEvent(self, event):
        """Double-clicking a segment inserts a waypoint at that position."""
        if event.button() == Qt.MouseButton.LeftButton and \
                self._insert_waypoint_at_segment(event.scenePos()) is not None:
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    # =========================================================================
    # Hover events
    # =========================================================================

    def hoverMoveEvent(self, event):
        idx = self._wp_index_at(event.scenePos(), self._WP_HOVER_RANGE)
        if idx != self._hovered_wp:
            self._hovered_wp = idx
            self.update()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        if self._hovered_wp is not None:
            self._hovered_wp = None
            self.update()
        super().hoverLeaveEvent(event)

    # =========================================================================
    # Context menu
    # =========================================================================

    def _show_wp_context_menu(self, wp_idx: int, event):
        menu   = QMenu()
        action = QAction(self.tr("Delete waypoint"), menu)
        action.triggered.connect(lambda: self._delete_waypoint(wp_idx))
        menu.addAction(action)
        view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        pos  = view.mapToGlobal(view.mapFromScene(event.scenePos())) if view else event.screenPos().toPoint()
        menu.exec(pos)

    def itemChange(self, change, value):
        if getattr(self, '_being_deleted', False):
            return value
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            if value and self._drag_mode == 'waypoint':
                return False
            self.update()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged:
            if self.editor and hasattr(self.editor, "theme_changed"):
                try:
                    self.editor.theme_changed.disconnect(self.on_theme_changed)
                except (TypeError, RuntimeError):
                    pass
                self.editor.theme_changed.connect(self.on_theme_changed)
                # Syncs with the current theme: the item may have been
                # created after the last toggle, never having received
                # the signal.
                self.on_theme_changed(getattr(self.editor, "is_light_theme", False))
        return super().itemChange(change, value)

    def on_theme_changed(self, is_light: bool) -> None:
        self.use_light_theme = is_light
        self.update()

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def prepare_delete(self):
        self._being_deleted = True
        self.hide()
        if self.source and self in self.source.connections:
            self.source.connections.remove(self)
        if self.target and self in self.target.connections:
            self.target.connections.remove(self)
        for anchor in (self.source_anchor, self.target_anchor):
            if anchor is None:
                continue
            anchor.refresh_junction_dot()
            self._cleanup_orphan_junction(anchor)
            self._merge_junction_if_collapsed(anchor)
        self.source = self.target = None
        self.prepareGeometryChange()

    @staticmethod
    def _merge_junction_if_collapsed(anchor) -> None:
        """Merges the two remaining legs of a JunctionNodeItem that just
        dropped to 2 live connections back together -- it's no longer a
        real T, so it no longer makes sense to exist as a separate node.

        Same deferred pattern as `_cleanup_orphan_junction`: creates the
        merged ConnectionItem and deletes the two old legs inside a
        QTimer.singleShot(0, ...), because prepare_delete() may already
        be running inside another deferral (DeleteManager or
        split_connection_at) -- nesting one more composes normally, the
        way the rest of the codebase already does.

        Removes the junction's node explicitly here (doesn't leave it to
        `_cleanup_orphan_junction`'s generic cascade, triggered when
        leg2.prepare_delete() zeroes the anchor's count): that cascade
        would schedule a SECOND, nested QTimer.singleShot(0, ...), which
        only settles on a second event-loop turn -- requiring two
        processEvents() instead of one to complete the whole merge.
        Doing the removal right here, within this single level of
        deferral, is safe (same composition already established) and
        keeps the whole merge settling within a single event-loop turn.
        """
        node = anchor.node
        if not isinstance(node, JunctionNodeItem) or anchor.connection_count() != 2:
            return

        leg1, leg2 = node.connections[0], node.connections[1]

        def _waypoints_toward_junction(leg):
            """Returns (other_side_node, other_side_anchor,
            waypoints_ordered_from_the_other_side_UP_TO_the_junction) --
            to become the HALF BEFORE the merge's pass-through point
            (wp1). The waypoints stored in `leg.waypoints` are already
            in source->target order; if the junction is the source (not
            the target), that order needs reversing."""
            if leg.target is node:
                return leg.source, leg.source_anchor, list(leg.waypoints)
            return leg.target, leg.target_anchor, list(reversed(leg.waypoints))

        def _waypoints_away_from_junction(leg):
            """Returns (other_side_node, other_side_anchor,
            waypoints_ordered_FROM_the_junction_to_the_other_side) -- to
            become the HALF AFTER the merge's pass-through point (wp2).
            Opposite direction from `_waypoints_toward_junction` --
            reusing the same function for both legs would reverse one
            of their orders and produce a diagonal segment (a real bug
            found while testing an actual merge: the pass-through point
            ended up linked to the wrong point of the second leg)."""
            if leg.source is node:
                return leg.target, leg.target_anchor, list(leg.waypoints)
            return leg.source, leg.source_anchor, list(reversed(leg.waypoints))

        def _merge():
            if not (leg1.scene() and leg2.scene()):
                return  # already handled by another path in the meantime

            p1_node, p1_anchor, wp1 = _waypoints_toward_junction(leg1)
            p2_node, p2_anchor, wp2 = _waypoints_away_from_junction(leg2)

            scene = leg1.scene()
            leg1.prepare_delete()
            leg2.prepare_delete()
            if leg1.scene():
                scene.removeItem(leg1)
            if leg2.scene():
                scene.removeItem(leg2)
            if node.scene():
                node.prepare_delete()
                scene.removeItem(node)
            ConnectionItem._rebuild_scene_index(scene)

            merged = ConnectionItem(p1_node, p1_anchor, p2_node, p2_anchor)
            merged.waypoints = wp1 + [QPointF(node.pos())] + wp2
            merged._waypoints_initialized = True
            merged.editor = leg1.editor or leg2.editor
            scene.addItem(merged)
            p1_node.connections.append(merged)
            p2_node.connections.append(merged)

            # wp1/wp2 were captured under the OLD legs' margins
            # (leg1/leg2, which pointed at the junction's "J" anchor) --
            # merged points directly at p1_node/p2_node, whose "ideal"
            # direction can differ from the junction's. Without this,
            # the segment near the pass-through point can come out
            # diagonal.
            merged.reanchor_waypoints()

            # Drops the junction's point (and any other) if it became
            # redundant -- 3 collinear points -- preserves it if it's a
            # real bend.
            merged._collapse_segment_corners()

            p1_anchor.refresh_junction_dot()
            p2_anchor.refresh_junction_dot()

        QTimer.singleShot(0, _merge)

    @staticmethod
    def _cleanup_orphan_junction(anchor) -> None:
        """Removes the JunctionNodeItem owning `anchor` if it just dropped
        to 0 live connections.

        A JunctionNodeItem has a 0x0 boundingRect()/shape() (no visible
        body by design) -- if both of its branches get deleted one at a
        time, it becomes an orphan node that's unclickable/
        unselectable/undeletable through normal UI, yet keeps getting
        serialized into every future save forever. Uses the SAME
        deferred pattern as split_connection_at/DeleteManager --
        prepare_delete() may already be running inside a
        QTimer.singleShot(0, ...) from DeleteManager or
        split_connection_at; nesting another singleShot(0, ...) here
        composes normally with that, the same way NodeItem.remove_anchor
        already composes with DeleteManager."""
        node = anchor.node
        if not isinstance(node, JunctionNodeItem) or anchor.connection_count() != 0:
            return

        def _remove_orphan_junction():
            scene = node.scene()
            if scene:
                node.prepare_delete()
                scene.removeItem(node)
                ConnectionItem._rebuild_scene_index(scene)
        QTimer.singleShot(0, _remove_orphan_junction)

    @staticmethod
    def _rebuild_scene_index(scene) -> None:
        """Forces a rebuild of the scene's spatial index (BSP) after
        removing items outside Qt's normal synchronous event cycle --
        same dance used by DeleteManager.do_delete() and
        NodeItem.remove_anchor(). Without this, the index keeps stale
        entries that corrupt a later spatial query (scene().items(pos),
        used by GraphicsView._connection_at on every mouseMoveEvent in
        CONNECT mode) -- reproduced for real: a "Windows fatal
        exception: access violation" minutes after a deferred removal
        without this rebuild."""
        scene.invalidate(scene.sceneRect(), QGraphicsScene.SceneLayer.AllLayers)
        current_index = scene.itemIndexMethod()
        scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        scene.setItemIndexMethod(current_index)
        scene.update()

    # =========================================================================
    # Serialization
    # =========================================================================

    def to_dict(self) -> dict:
        d = {
            "source": {"node": self.source.id, "anchor": self.source_anchor.name},
            "target": {"node": self.target.id, "anchor": self.target_anchor.name},
        }
        if self.waypoints:
            d["waypoints"] = [{"x": wp.x(), "y": wp.y()} for wp in self.waypoints]
        return d

    @classmethod
    def from_dict(cls, data: dict, node_index: dict):
        source_node   = node_index[data["source"]["node"]]
        target_node   = node_index[data["target"]["node"]]
        source_anchor = source_node.anchors[data["source"]["anchor"]]
        target_anchor = target_node.anchors[data["target"]["anchor"]]
        conn = cls(source_node, source_anchor, target_node, target_anchor)
        for wp in data.get("waypoints", []):
            conn.waypoints.append(QPointF(wp["x"], wp["y"]))
        conn._waypoints_initialized = True
        source_node.connections.append(conn)
        target_node.connections.append(conn)
        # Without this, every undo/redo (which rebuilds the whole scene
        # via _restore_snapshot -> deserialize_scene) would erase the
        # junction dot until the user moved the mouse over the anchor
        # again.
        source_anchor.refresh_junction_dot()
        target_anchor.refresh_junction_dot()
        # Seeds the anchors' position/direction cache with the current
        # values (== the values at save time, since the anchors haven't
        # moved since then) BEFORE the repair below. Without this,
        # `_last_p1_out`/`_last_p2_in`/`_last_exit_dir`/`_last_entry_dir`
        # stay at `__init__`'s defaults and
        # `adjust_waypoints_for_node_move`'s "pristine route" check never
        # fires here -- any automatic 3+ point route (hvhv/vhvh) loaded
        # from the file gains a spurious bridge (zero-length, sitting
        # right on top of the anchor) just from this missing history,
        # and that bridge gets persisted back on the next save.
        if conn._anchors_in_scene():
            _, _, p1_out, p2_in, exit_dir, entry_dir = conn._compute_exit_entry()
            conn._last_p1_out, conn._last_p2_in = QPointF(p1_out), QPointF(p2_in)
            conn._last_exit_dir, conn._last_entry_dir = exit_dir, entry_dir
        # Repairs non-orthogonal waypoints saved by older versions.
        # Safe for A* waypoints since the sanity check is only wp->wp.
        conn.adjust_waypoints_for_node_move()
        return conn

    # =========================================================================
    # Simulation state
    # =========================================================================

    def set_state(self, value: float):
        if self.state != value:
            self.state = value
            self.update()

    def reset_visual_state(self):
        self.state = 0
        self.update()