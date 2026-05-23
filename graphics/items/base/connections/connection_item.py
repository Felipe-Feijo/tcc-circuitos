"""Item gráfico de conexão entre dois âncoras do diagrama."""

# graphics/items/connection_item.py
from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtGui import QColor, QPainterPath, QPen, QPainter, QPainterPathStroker
from PyQt6.QtCore import Qt, QPointF, QRectF
from graphics.items.base.diagram_item_base import DiagramItemBase


class ConnectionItem(DiagramItemBase):
    def __init__(self, source_node, source_anchor, target_node=None, target_anchor=None):
        DiagramItemBase.__init__(self)

        self.state: float = 0.0

        self.id = frozenset([
            source_anchor.id,
            target_anchor.id if target_anchor else None
        ])

        self.source = source_node
        self.source_anchor = source_anchor
        self.target = target_node
        self.target_anchor = target_anchor

        self.temp_target_pos = None
        self._being_deleted = False

        self.waypoints: list[QPointF] = []
        self._waypoints_initialized: bool = False
        self._hovered_wp: int | None = None
        self._drag_mode = None          # 'waypoint' | 'segment'
        self._drag_wp_index: int | None = None
        self._drag_is_horizontal: bool = True
        self._drag_original_wps: list = []
        self._last_exit_dir:  str = "right"
        self._last_entry_dir: str = "left"
        self._selected_wp: int | None = None

        self.setPos(0, 0)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        if self.domain == "hydraulic":
            self.pen = QPen(Qt.GlobalColor.cyan, 3)
        else:
            self.pen = QPen(Qt.GlobalColor.white, 3)

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
        path = QPainterPath()
        points = self.get_path_points()
        if len(points) < 2:
            return path
        line_path = QPainterPath()
        line_path.moveTo(points[0])
        for point in points[1:]:
            line_path.lineTo(point)
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
        min_x = min(p.x() for p in points)
        max_x = max(p.x() for p in points)
        min_y = min(p.y() for p in points)
        max_y = max(p.y() for p in points)
        return QRectF(min_x - margin, min_y - margin,
                      max_x - min_x + 2 * margin, max_y - min_y + 2 * margin)

    # =========================================================================
    # Paint
    # =========================================================================

    def paint(self, painter: QPainter, option, widget=None):
        points = self.get_path_points()
        if len(points) < 2:
            return
        is_preview = self.target_anchor is None
        pen = self._get_pen(is_preview)
        painter.setPen(pen)
        for start, end in zip(points, points[1:]):
            painter.drawLine(start, end)
        if self.waypoints:
            self._draw_waypoint_handles(painter)
        if not is_preview and self.domain == "hydraulic" and self.state != "ERR" and not self.isSelected():
            if len(points) >= 3:
                self._draw_flow_arrows(painter, points, pen)

    def _get_pen(self, is_preview: bool = False) -> QPen:
        if is_preview:
            pen = QPen(QColor(150, 150, 150), 2)
            pen.setStyle(Qt.PenStyle.DashLine)
            return pen
        if self.isSelected():
            return QPen(Qt.GlobalColor.blue, 3)
        if self.domain == "pneumatic" and self.state == 1:
            return QPen(Qt.GlobalColor.green, 3)
        if self.domain == "electric" and self.state == 1:
            return QPen(Qt.GlobalColor.yellow, 3)
        if self.domain == "hydraulic":
            if self.state == "ERR":
                return QPen(Qt.GlobalColor.red, 3)
            if self.state == "PRESSURIZING":
                return QPen(QColor(255, 140, 0), 3)
            if self.state > 0:
                return QPen(Qt.GlobalColor.blue, 3)
            if self.state < 0:
                return QPen(QColor(100, 180, 255), 3)
            return QPen(Qt.GlobalColor.cyan, 3)
        return self.pen

    def _draw_flow_arrows(self, painter: QPainter, points: list, pen: QPen):
        arrow_offset = 4
        flow_a = getattr(self.source_anchor, "flow", 0.0)
        if not isinstance(flow_a, str) and abs(flow_a) > 1e-10:
            exit_dir = self._get_exit_direction()
            p1_arrow = self._apply_margin(points[1], exit_dir, -arrow_offset)
            self._draw_arrow_at(painter, p1_arrow, exit_dir, flow_a, pen)
        if self.target_anchor:
            flow_b = getattr(self.target_anchor, "flow", 0.0)
            if not isinstance(flow_b, str) and abs(flow_b) > 1e-10:
                is_internal = self.source_anchor.node == self.target_anchor.node
                exit_key = "internal" if is_internal else "external"
                entry_dirs = self.target_anchor.exit_directions.get(exit_key, ["left"])
                entry_dir = self._choose_best_exit_direction(points[-1], points[0], entry_dirs)
                p2_arrow = self._apply_margin(points[-2], entry_dir, -arrow_offset)
                self._draw_arrow_at(painter, p2_arrow, entry_dir, flow_b, pen)

    def _draw_arrow_at(self, painter: QPainter, point: QPointF, direction: str, flow: float, pen: QPen):
        size = 6
        dir_map = {"right": (1, 0), "left": (-1, 0), "bottom": (0, 1), "top": (0, -1)}
        ux, uy = dir_map.get(direction, (1, 0))
        if flow > 0:
            ux, uy = -ux, -uy
        tip   = QPointF(point.x() + ux * size,       point.y() + uy * size)
        base  = QPointF(point.x() - ux * size,       point.y() - uy * size)
        left  = QPointF(base.x() - uy * size * 0.6,  base.y() + ux * size * 0.6)
        right = QPointF(base.x() + uy * size * 0.6,  base.y() - ux * size * 0.6)
        from PyQt6.QtGui import QPolygonF, QBrush
        painter.setBrush(QBrush(pen.color()))
        painter.setPen(pen)
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
            p2 = target_anchor.scenePos()
            is_preview = False
        elif self.temp_target_pos:
            p2 = self.temp_target_pos
            is_preview = True
        else:
            return [p1]

        is_internal = (target_anchor and
                       source_anchor.node == target_anchor.node)
        exit_key = "internal" if is_internal else "external"
        source_dirs = source_anchor.exit_directions.get(exit_key, ["right"])
        exit_dir = self._choose_best_exit_direction(p1, p2, source_dirs)

        source_margin, _ = self._compute_margins(p1, p2)
        p1_out = self._apply_margin(p1, exit_dir, source_margin)
        points = [p1, p1_out]

        if is_preview:
            dx = abs(p2.x() - p1_out.x())
            dy = abs(p2.y() - p1_out.y())
            middle = self._hvh(p1_out, p2) if dx > dy else self._vhv(p1_out, p2)
            points.extend(middle)
            points.append(p2)
            return points

        target_dirs = target_anchor.exit_directions.get(exit_key, ["left"])
        _, target_margin = self._compute_margins(p1, p2)

        if not self._waypoints_initialized:
            entry_dir = self._choose_best_exit_direction(p2, p1, target_dirs)
            p2_in = self._apply_margin(p2, entry_dir, target_margin)
            self._waypoints_initialized = True
            self.waypoints = [QPointF(pt) for pt in
                              self._route_between_points(p1_out, p2_in, exit_dir, entry_dir)]
            # Garante ortogonalidade nos waypoints recém-criados
            self.adjust_waypoints_for_node_move()
        else:
            # Waypoints já existem (gerados pelo A* ou por edição manual).
            # Derivar entry_dir e exit_dir a partir dos waypoints reais,
            # para que p1_out e p2_in sejam coerentes com eles.
            if self.waypoints:
                first_wp = self.waypoints[0]
                dx0 = first_wp.x() - p1.x()
                dy0 = first_wp.y() - p1.y()
                if abs(dy0) >= abs(dx0):
                    exit_dir = "bottom" if dy0 > 0 else "top"
                else:
                    exit_dir = "right" if dx0 > 0 else "left"
                p1_out = self._apply_margin(p1, exit_dir, source_margin)

                last_wp = self.waypoints[-1]
                dx1 = p2.x() - last_wp.x()
                dy1 = p2.y() - last_wp.y()
                # entry_dir = direção de onde a linha CHEGA em p2.
                # p2_in = _apply_margin(p2, entry_dir) deve ficar entre last_wp e p2,
                # então entry_dir é oposto ao vetor last_wp→p2:
                # se dy1>0 (linha vem de cima, desce até p2) → entry_dir=top (p2_in acima de p2)
                # se dy1<0 (linha vem de baixo, sobe até p2)  → entry_dir=bottom
                if abs(dy1) >= abs(dx1):
                    entry_dir = "top" if dy1 > 0 else "bottom"
                else:
                    entry_dir = "left" if dx1 > 0 else "right"
            else:
                entry_dir = self._choose_best_exit_direction(p2, p1, target_dirs)

            p2_in = self._apply_margin(p2, entry_dir, target_margin)

        self._last_exit_dir  = exit_dir
        self._last_entry_dir = entry_dir

        points[-1] = p1_out  # atualizar p1_out após possível recálculo
        points.extend(self.waypoints)
        points.append(p2_in)
        points.append(p2)
        return points

    def _compute_margins(self, p1: QPointF, p2: QPointF):
        dist = abs(p2.x() - p1.x()) + abs(p2.y() - p1.y())
        adaptive = min(18, max(6, dist * 0.15))
        source_margin = getattr(self.source_anchor, "margin", None) or adaptive
        if self.target_anchor:
            target_margin = getattr(self.target_anchor, "margin", None) or adaptive
        else:
            target_margin = adaptive
        return source_margin, target_margin

    def _choose_best_exit_direction(self, from_point: QPointF, to_point: QPointF, allowed_dirs: list) -> str:
        if len(allowed_dirs) == 1:
            return allowed_dirs[0]
        dx = to_point.x() - from_point.x()
        dy = to_point.y() - from_point.y()
        scores = {}
        for d in allowed_dirs:
            if   d == "right"  and dx > 0: scores[d] =  abs(dx)
            elif d == "left"   and dx < 0: scores[d] =  abs(dx)
            elif d == "bottom" and dy > 0: scores[d] =  abs(dy)
            elif d == "top"    and dy < 0: scores[d] =  abs(dy)
            else:                          scores[d] = -1000
        return max(scores, key=scores.get)

    def _apply_margin(self, point: QPointF, direction: str, margin: float) -> QPointF:
        if direction == "left":   return QPointF(point.x() - margin, point.y())
        if direction == "right":  return QPointF(point.x() + margin, point.y())
        if direction == "top":    return QPointF(point.x(), point.y() - margin)
        if direction == "bottom": return QPointF(point.x(), point.y() + margin)
        return point

    def _get_exit_direction(self) -> str:
        """Returns the exit direction from the source anchor toward the target."""
        if not self.source_anchor:
            return "right"
        is_internal = (self.target_anchor and
                       self.source_anchor.node == self.target_anchor.node)
        exit_key = "internal" if is_internal else "external"
        dirs = self.source_anchor.exit_directions.get(exit_key, ["right"])
        if self.target_anchor:
            p1 = self.source_anchor.scenePos()
            p2 = self.target_anchor.scenePos()
            return self._choose_best_exit_direction(p1, p2, dirs)
        return dirs[0] if dirs else "right"

    def _compute_exit_entry(self):
        """
        Returns (p1, p2, p1_out, p2_in, exit_dir, entry_dir) for the current
        source/target anchors. Assumes both anchors exist and are in the scene.
        """
        p1 = self.source_anchor.scenePos()
        p2 = self.target_anchor.scenePos()

        is_internal = self.source_anchor.node == self.target_anchor.node
        exit_key = "internal" if is_internal else "external"

        source_dirs = self.source_anchor.exit_directions.get(exit_key, ["right"])
        exit_dir    = self._choose_best_exit_direction(p1, p2, source_dirs)

        target_dirs = self.target_anchor.exit_directions.get(exit_key, ["left"])
        entry_dir   = self._choose_best_exit_direction(p2, p1, target_dirs)

        source_margin, target_margin = self._compute_margins(p1, p2)
        p1_out = self._apply_margin(p1, exit_dir,  source_margin)
        p2_in  = self._apply_margin(p2, entry_dir, target_margin)

        return p1, p2, p1_out, p2_in, exit_dir, entry_dir

    # =========================================================================
    # Routing helpers
    # =========================================================================

    def _route_between_points(self, p1_out: QPointF, p2_in: QPointF, exit_dir: str, entry_dir: str) -> list:
        dx = p2_in.x() - p1_out.x()
        dy = p2_in.y() - p1_out.y()
        is_exit_h  = exit_dir  in ("left", "right")
        is_entry_h = entry_dir in ("left", "right")
        exit_conflict_h  = (exit_dir  == "left"   and dx > 0) or (exit_dir  == "right"  and dx < 0)
        exit_conflict_v  = (exit_dir  == "top"    and dy > 0) or (exit_dir  == "bottom" and dy < 0)
        entry_conflict_h = (entry_dir == "left"   and dx < 0) or (entry_dir == "right"  and dx > 0)
        entry_conflict_v = (entry_dir == "top"    and dy < 0) or (entry_dir == "bottom" and dy > 0)

        def four_seg(p1, p2):
            if dy != 0:
                return self._hvhv(p1, p2) if dy > 0 else self._vhvh(p1, p2)
            return self._hvhv(p1, p2) if dx > 0 else self._vhvh(p1, p2)

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

    def _vhv(self, p1, p2):
        mid_y = (p1.y() + p2.y()) / 2
        return [QPointF(p1.x(), mid_y), QPointF(p2.x(), mid_y)]

    def _hvh(self, p1, p2):
        mid_x = (p1.x() + p2.x()) / 2
        return [QPointF(mid_x, p1.y()), QPointF(mid_x, p2.y())]

    def _hvhv(self, p1, p2):
        mid_x = (p1.x() + p2.x()) / 2
        mid_y = (p1.y() + p2.y()) / 2
        return [QPointF(mid_x, p1.y()), QPointF(mid_x, mid_y), QPointF(p2.x(), mid_y)]

    def _vhvh(self, p1, p2):
        mid_x = (p1.x() + p2.x()) / 2
        mid_y = (p1.y() + p2.y()) / 2
        return [QPointF(p1.x(), mid_y), QPointF(mid_x, mid_y), QPointF(mid_x, p2.y())]

    def update_temp_endpoint(self, scene_pos: QPointF):
        self.prepareGeometryChange()
        self.temp_target_pos = scene_pos
        self.update()

    def update_position(self):
        if getattr(self, '_being_deleted', False):
            return
        self.prepareGeometryChange()
        self.update()

    def adjust_waypoints_for_node_move(self) -> None:
        """Repair any non-orthogonal segments after a node move.

        Forward pass over [p1_out, wp0, …, wpN, p2_in]: for each diagonal
        segment, snaps the mutable waypoint to keep the path axis-aligned,
        seeded by exit_dir so the first segment is always correct.
        """
        if getattr(self, '_being_deleted', False):
            return
        if not self._waypoints_initialized:
            return
        if not self.source_anchor or not self.target_anchor:
            return
        if not self.source_anchor.scene() or not self.target_anchor.scene():
            return
        if not self.waypoints:
            return

        _, _, p1_out, p2_in, exit_dir, entry_dir = self._compute_exit_entry()

        SNAP = 0.5

        def is_ortho(a: QPointF, b: QPointF) -> bool:
            return abs(a.x() - b.x()) < SNAP or abs(a.y() - b.y()) < SNAP

        # Snap the last waypoint to follow p2_in (entry direction),
        # and the first waypoint to follow p1_out (exit direction).
        # This keeps the path orthogonal when source or target nodes move,
        # without inserting extra waypoints.
        wps = [QPointF(wp) for wp in self.waypoints]

        entry_h = entry_dir in ("left", "right")
        exit_h  = exit_dir  in ("left", "right")

        # First waypoint must share the axis perpendicular to exit_dir with p1_out
        if exit_h:
            wps[0] = QPointF(wps[0].x(), p1_out.y())
        else:
            wps[0] = QPointF(p1_out.x(), wps[0].y())

        # Last waypoint must share the axis perpendicular to entry_dir with p2_in
        if entry_h:
            wps[-1] = QPointF(wps[-1].x(), p2_in.y())
        else:
            wps[-1] = QPointF(p2_in.x(), wps[-1].y())

        self.waypoints = wps
        self.prepareGeometryChange()
        self.update()

    # =========================================================================
    # Waypoints — constants
    # =========================================================================

    _WP_HIT_RADIUS    = 10
    _WP_HOVER_RANGE   = 20
    _SEG_HIT_DIST     = 8
    _WP_VISIBLE_RANGE = 40

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
        r = radius if radius is not None else self._WP_HIT_RADIUS
        r2 = r ** 2
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
        inner = pts[1:-1]
        best_d, result = self._SEG_HIT_DIST + 1, None
        for i in range(len(inner) - 1):
            a, b = inner[i], inner[i+1]
            d = self._dist_point_to_seg(px, py, a.x(), a.y(), b.x(), b.y())
            if d < best_d:
                best_d = d
                result = (i, QPointF(a), QPointF(b))
        return result

    # =========================================================================
    # Waypoints — drawing
    # =========================================================================

    def _draw_waypoint_handles(self, painter: QPainter):
        if self._hovered_wp is None and self._drag_mode is None and self._selected_wp is None:
            return
        r = self._WP_HIT_RADIUS
        dragging_idx = self._drag_wp_index if self._drag_mode is not None else None
        hover_wp = self._hovered_wp
        visible_range2 = self._WP_VISIBLE_RANGE ** 2

        ref_pos: QPointF | None = None
        if hover_wp is not None and hover_wp < len(self.waypoints):
            ref_pos = self.waypoints[hover_wp]
        elif dragging_idx is not None and dragging_idx < len(self.waypoints):
            ref_pos = self.waypoints[dragging_idx]
        elif self._selected_wp is not None and self._selected_wp < len(self.waypoints):
            ref_pos = self.waypoints[self._selected_wp]

        for i, wp in enumerate(self.waypoints):
            if ref_pos is not None:
                d2 = (wp.x() - ref_pos.x())**2 + (wp.y() - ref_pos.y())**2
                if d2 > visible_range2:
                    continue

            if self._drag_mode == 'waypoint' and i == dragging_idx:
                fill, border = QColor(220, 40, 40), QColor(255, 120, 120)
            elif i == self._selected_wp:
                fill, border = QColor(60, 120, 255, 230), QColor(120, 180, 255, 255)
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

    def _reroute_waypoints(self):
        """Discards current waypoints and recomputes the route from scratch."""
        if not self.source_anchor or not self.target_anchor:
            return
        if not self.source_anchor.scene() or not self.target_anchor.scene():
            return
        _, _, p1_out, p2_in, exit_dir, entry_dir = self._compute_exit_entry()
        self.waypoints = [QPointF(pt) for pt in
                          self._route_between_points(p1_out, p2_in, exit_dir, entry_dir)]
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
        """
        Inserts a single waypoint on the segment closest to *scene_pos*.
        Returns the insertion index, or None if no segment was hit.
        """
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
        self._drag_mode = None
        self._drag_wp_index = None
        self._drag_is_horizontal = True
        self._drag_original_wps = []

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
            self._selected_wp = None if self._selected_wp == idx else idx
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self.setSelected(False)
            self._drag_mode = 'waypoint'
            self._drag_wp_index = idx
            self._drag_original_wps = [QPointF(p) for p in self.waypoints]
            self.update()
            event.accept()
            return

        if self._selected_wp is not None:
            self._selected_wp = None
            self.update()

        hit = self._seg_hit_at(sp)
        if hit is not None:
            ins_idx, seg_a, seg_b = hit
            is_horizontal = abs(seg_a.y() - seg_b.y()) < 1.0
            self._drag_is_horizontal = is_horizontal
            self.prepareGeometryChange()
            self.waypoints.insert(ins_idx,     QPointF(seg_a))
            self.waypoints.insert(ins_idx + 1, QPointF(seg_b))
            self._drag_mode = 'segment'
            self._drag_wp_index = ins_idx
            self.update()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        sp = event.scenePos()

        if self._drag_mode == 'waypoint':
            i = self._drag_wp_index
            if i is not None and 0 <= i < len(self._drag_original_wps):
                wps = [QPointF(p) for p in self._drag_original_wps]
                orig = wps[i]

                prev_h = i > 0          and abs(wps[i-1].y() - orig.y()) < 0.5
                prev_v = i > 0          and abs(wps[i-1].x() - orig.x()) < 0.5
                next_h = i < len(wps)-1 and abs(wps[i+1].y() - orig.y()) < 0.5
                next_v = i < len(wps)-1 and abs(wps[i+1].x() - orig.x()) < 0.5

                new_x = sp.x() if (prev_v or next_v) else orig.x()
                new_y = sp.y() if (prev_h or next_h) else orig.y()
                wps[i] = QPointF(new_x, new_y)

                if i > 0:
                    if prev_h: wps[i-1] = QPointF(wps[i-1].x(), new_y)
                    elif prev_v: wps[i-1] = QPointF(new_x, wps[i-1].y())
                if i < len(wps) - 1:
                    if next_h: wps[i+1] = QPointF(wps[i+1].x(), new_y)
                    elif next_v: wps[i+1] = QPointF(new_x, wps[i+1].y())

                self.waypoints = wps
                self._hovered_wp = i
                self.prepareGeometryChange()
                self.update()
            event.accept()
            return

        if self._drag_mode == 'segment':
            i = self._drag_wp_index
            if i is not None and i + 1 < len(self.waypoints):
                self.prepareGeometryChange()
                wp1 = self.waypoints[i]
                wp2 = self.waypoints[i + 1]
                if self._drag_is_horizontal:
                    self.waypoints[i]     = QPointF(wp1.x(), sp.y())
                    self.waypoints[i + 1] = QPointF(wp2.x(), sp.y())
                else:
                    self.waypoints[i]     = QPointF(sp.x(), wp1.y())
                    self.waypoints[i + 1] = QPointF(sp.x(), wp2.y())
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
            self._collapse_segment_corners()
        self._reset_drag_state()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        super().mouseReleaseEvent(event)
        if was_waypoint_drag and self.isSelected():
            self.setSelected(False)

    def _collapse_segment_corners(self):
        if not self.waypoints:
            return
        pts = self.get_path_points()
        p1_out = pts[1]  if len(pts) > 1 else None
        p2_in  = pts[-2] if len(pts) > 1 else None

        def neighbour(i):
            if i < 0:                    return p1_out
            if i >= len(self.waypoints): return p2_in
            return self.waypoints[i]

        changed = True
        while changed and self.waypoints:
            changed = False
            i = 0
            while i < len(self.waypoints):
                prev = neighbour(i - 1)
                curr = self.waypoints[i]
                nxt  = neighbour(i + 1)
                if prev is None or nxt is None:
                    i += 1
                    continue
                ab_h = abs(prev.y() - curr.y()) < 0.5
                bc_h = abs(curr.y() - nxt.y())  < 0.5
                ab_v = abs(prev.x() - curr.x()) < 0.5
                bc_v = abs(curr.x() - nxt.x())  < 0.5
                if (ab_h and bc_h) or (ab_v and bc_v):
                    self.waypoints.pop(i)
                    changed = True
                else:
                    i += 1
        self.prepareGeometryChange()
        self.adjust_waypoints_for_node_move()

    def mouseDoubleClickEvent(self, event):
        """Double-click on a segment inserts a waypoint at that position."""
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(event)
            return
        if self._insert_waypoint_at_segment(event.scenePos()) is not None:
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
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction
        menu = QMenu()
        delete_action = QAction("Deletar waypoint", menu)
        delete_action.triggered.connect(lambda: self._delete_waypoint(wp_idx))
        menu.addAction(delete_action)
        view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        if view:
            screen_pos = view.mapToGlobal(view.mapFromScene(event.scenePos()))
            menu.exec(screen_pos)
        else:
            menu.exec(event.screenPos().toPoint())

    def itemChange(self, change, value):
        if getattr(self, '_being_deleted', False):
            return value
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            if value and self._drag_mode == 'waypoint':
                return False
            self.update()
        return super().itemChange(change, value)

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
        self.source = None
        self.target = None
        self.prepareGeometryChange()

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