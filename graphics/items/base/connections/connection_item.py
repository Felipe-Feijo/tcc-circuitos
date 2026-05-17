# graphics/items/connection_item.py
from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtGui import QColor, QPainterPath, QPen, QPainter, QPainterPathStroker
from PyQt6.QtCore import Qt, QPointF, QRectF
from graphics.items.base.diagram_item_base import DiagramItemBase


class ConnectionItem(DiagramItemBase):
    def __init__(self, source_node, source_anchor, target_node=None, target_anchor=None):
        DiagramItemBase.__init__(self)

        self.state: float = 0.0  # 0 = desligado, 1 = ligado (pneumatic/electric), 0-1 contínuo (hidraulic)

        self.id = frozenset([
            source_anchor.id,
            target_anchor.id if target_anchor else None
        ])

        self.source = source_node
        self.source_anchor = source_anchor
        self.target = target_node
        self.target_anchor = target_anchor

        self.temp_target_pos = None
        self._being_deleted = False  # Flag para evitar loops de atualização durante deleção

        # Waypoints manuais em coordenadas de cena.
        # Vazio = roteamento geométrico automático (comportamento original).
        self.waypoints: list[QPointF] = []
        self._waypoints_initialized: bool = False  # True após primeira inicialização automática
        self._hovered_wp: int | None = None
        self._drag_mode = None
        self._drag_wp_index: int | None = None
        self._drag_is_horizontal: bool = True
        self._drag_original_wps: list = []
        self._pending_seg_hit = None
        self._pending_press_pos: QPointF = QPointF()
        self._last_exit_dir:  str = "right"
        self._last_entry_dir: str = "left"

        self.setPos(0, 0)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        # Pens para cada domínio
        if self.domain == "pneumatic":
            self.pen = QPen(Qt.GlobalColor.white, 3)
        elif self.domain == "electric":
            self.pen = QPen(Qt.GlobalColor.white, 3)
        elif self.domain == "hydraulic":
            # ainda placeholder
            self.pen = QPen(Qt.GlobalColor.cyan, 3)
        
        self.setZValue(-10)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.update()

    @property
    def domain(self):
        return getattr(self.source_anchor, "domain")

    def shape(self) -> QPainterPath:
        """Define a área clicável/selecionável seguindo o caminho da linha"""
        path = QPainterPath()
        points = self.get_path_points()
        
        if len(points) < 2:
            return path
        
        # Cria um "stroke" ao redor da linha para facilitar seleção
        line_path = QPainterPath()
        line_path.moveTo(points[0])
        for point in points[1:]:
            line_path.lineTo(point)
        
        # Cria uma área de 8px ao redor da linha (facilita clique/seleção)
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

        return QRectF(
            min_x - margin,
            min_y - margin,
            max_x - min_x + 2 * margin,
            max_y - min_y + 2 * margin
        )

    def paint(self, painter: QPainter, option, widget=None):
        points = self.get_path_points()
        if len(points) < 2:
            return

        if self.isSelected():
            pen = QPen(Qt.GlobalColor.blue, 3)
        else:
            if self.domain == "pneumatic" and self.state == 1:
                pen = QPen(Qt.GlobalColor.green, 3)
            elif self.domain == "electric" and self.state == 1:
                pen = QPen(Qt.GlobalColor.yellow, 3)
            elif self.domain == "hydraulic":
                if self.state == "ERR":
                    pen = QPen(Qt.GlobalColor.red, 3)
                elif self.state == "PRESSURIZING":
                    pen = QPen(QColor(255, 140, 0), 3)  # laranja
                elif self.state > 0:
                    pen = QPen(Qt.GlobalColor.blue, 3)
                elif self.state < 0:
                    pen = QPen(QColor(100, 180, 255), 3)
                else:
                    pen = QPen(Qt.GlobalColor.cyan, 3)
            else:
                pen = self.pen

        painter.setPen(pen)
        for start, end in zip(points, points[1:]):
            painter.drawLine(start, end)

        if self.domain == "hydraulic" and self.state != "ERR" and not self.isSelected():
            if len(points) >= 3:
                arrow_offset = 4

                # triângulo da source anchor
                flow_a = getattr(self.source_anchor, "flow", 0.0)
                if not isinstance(flow_a, str) and abs(flow_a) > 1e-10:
                    p1_out = points[1]
                    exit_dir = self._get_exit_direction()
                    p1_arrow = self._apply_margin(p1_out, exit_dir, -arrow_offset)
                    self._draw_arrow_at(painter, p1_arrow, exit_dir, flow_a, pen)

                # triângulo da target anchor
                if self.target_anchor:
                    flow_b = getattr(self.target_anchor, "flow", 0.0)
                    if not isinstance(flow_b, str) and abs(flow_b) > 1e-10:
                        p2_in = points[-2]
                        is_internal = self.source_anchor.node == self.target_anchor.node
                        exit_key = "internal" if is_internal else "external"
                        entry_dirs = self.target_anchor.exit_directions.get(exit_key, ["left"])
                        entry_dir = self._choose_best_exit_direction(points[-1], points[0], entry_dirs)
                        p2_arrow = self._apply_margin(p2_in, entry_dir, -arrow_offset)
                        self._draw_arrow_at(painter, p2_arrow, entry_dir, flow_b, pen)

    def _draw_arrow_at(self, painter, point, direction, flow, pen):
        size = 6

        # direção base do segmento
        dir_map = {
            "right":  ( 1,  0),
            "left":   (-1,  0),
            "bottom": ( 0,  1),
            "top":    ( 0, -1),
        }
        ux, uy = dir_map.get(direction, (1, 0))

        # sinal do fluxo determina o sentido
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

        # Determina se é conexão interna ou externa
        is_internal = (self.target_anchor and 
                    self.source_anchor.node == self.target_anchor.node)
        
        # Obtém direções permitidas
        exit_key = "internal" if is_internal else "external"
        source_dirs = self.source_anchor.exit_directions.get(exit_key, ["right"])
        
        # Escolhe a melhor direção de saída
        exit_dir = self._choose_best_exit_direction(p1, p2, source_dirs)

        # margem adaptativa (fallback)
        dist = abs(p2.x() - p1.x()) + abs(p2.y() - p1.y())
        adaptive_margin = min(18, max(6, dist * 0.15))

        # margem por anchor — se definida, usa exatamente; senão usa adaptativo
        source_margin = getattr(self.source_anchor, "margin", None)
        if source_margin is None:
            source_margin = adaptive_margin

        if self.target_anchor:
            target_margin = getattr(self.target_anchor, "margin", None)
            if target_margin is None:
                target_margin = adaptive_margin
        else:
            target_margin = adaptive_margin

        points = [p1]

        # Segmento de saída da source
        p1_out = self._apply_margin(p1, exit_dir, source_margin)
        points.append(p1_out)

        # ============================================
        # MODO PREVIEW: caminho simples VHV ou HVH
        # ============================================
        if is_preview:
            dx = abs(p2.x() - p1_out.x())
            dy = abs(p2.y() - p1_out.y())

            if dx > dy:
                points.extend(self._hvh(p1_out, p2))
            else:
                points.extend(self._vhv(p1_out, p2))

            points.append(p2)
            return points

        # ============================================
        # MODO NORMAL: lógica completa
        # ============================================
        
        # Obtém direção de entrada do target
        target_dirs = self.target_anchor.exit_directions.get(exit_key, ["left"])
        entry_dir = self._choose_best_exit_direction(p2, p1, target_dirs)

        # Segmento de entrada no target
        p2_in = self._apply_margin(p2, entry_dir, target_margin)

        # Guarda dirs para uso no mouseReleaseEvent
        self._last_exit_dir  = exit_dir
        self._last_entry_dir = entry_dir

        # ── Inicializa waypoints a partir do caminho geométrico (primeira vez) ─
        if not self._waypoints_initialized:
            self._waypoints_initialized = True
            middle_points = self._route_between_points(p1_out, p2_in, exit_dir, entry_dir)
            # Salva todos os pontos do caminho completo como waypoints
            # (p1_out e p2_in são os extremos fixos, não ficam nos waypoints)
            self.waypoints = [QPointF(pt) for pt in middle_points]

        # ── Usa waypoints para construir o caminho ──────────────────────
        middle_points = self._build_ortho_points(p1_out, p2_in, exit_dir, entry_dir)
        points.extend(middle_points)

        # Adiciona o segmento final
        points.append(p2_in)
        points.append(p2)

        return points


    def _choose_best_exit_direction(self, from_point, to_point, allowed_dirs):
        """Escolhe a melhor direção de saída baseada na posição relativa"""
        if len(allowed_dirs) == 1:
            return allowed_dirs[0]
        
        dx = to_point.x() - from_point.x()
        dy = to_point.y() - from_point.y()
        
        # Calcula scores para cada direção permitida
        scores = {}
        for direction in allowed_dirs:
            if direction == "right" and dx > 0:
                scores[direction] = abs(dx)
            elif direction == "left" and dx < 0:
                scores[direction] = abs(dx)
            elif direction == "bottom" and dy > 0:
                scores[direction] = abs(dy)
            elif direction == "top" and dy < 0:
                scores[direction] = abs(dy)
            else:
                scores[direction] = -1000  # Penaliza direções contrárias
        
        return max(scores, key=scores.get)


    def _apply_margin(self, point, direction, margin):
        """Aplica margem em uma direção específica"""
        if direction == "left":
            return QPointF(point.x() - margin, point.y())
        elif direction == "right":
            return QPointF(point.x() + margin, point.y())
        elif direction == "top":
            return QPointF(point.x(), point.y() - margin)
        elif direction == "bottom":
            return QPointF(point.x(), point.y() + margin)
        return point


    def _route_between_points(self, p1_out, p2_in, exit_dir, entry_dir):
        dx = p2_in.x() - p1_out.x()
        dy = p2_in.y() - p1_out.y()

        is_exit_horizontal = exit_dir in ("left", "right")
        is_entry_horizontal = entry_dir in ("left", "right")

        exit_conflict_h = (exit_dir == "left" and dx > 0) or (exit_dir == "right" and dx < 0)
        exit_conflict_v = (exit_dir == "top" and dy > 0) or (exit_dir == "bottom" and dy < 0)

        entry_conflict_h = (entry_dir == "left" and dx < 0) or (entry_dir == "right" and dx > 0)
        entry_conflict_v = (entry_dir == "top" and dy < 0) or (entry_dir == "bottom" and dy > 0)

        def four_seg(p1, p2):
            # dy > 0: p2 está abaixo → termina descendo → hvhv
            # dy < 0: p2 está acima → termina subindo → vhvh
            # dy == 0: decide pelo dx
            if dy != 0:
                return self._hvhv(p1, p2) if dy > 0 else self._vhvh(p1, p2)
            else:
                return self._hvhv(p1, p2) if dx > 0 else self._vhvh(p1, p2)

        # Exit horizontal
        if is_exit_horizontal:
            if exit_conflict_h:
                return four_seg(p1_out, p2_in) if entry_conflict_v else self._vhv(p1_out, p2_in)
            if is_entry_horizontal:
                return four_seg(p1_out, p2_in) if entry_conflict_h else self._hvh(p1_out, p2_in)
            return self._hvh(p1_out, p2_in)

        # Exit vertical
        else:
            if exit_conflict_v:
                return four_seg(p1_out, p2_in) if entry_conflict_h else self._hvh(p1_out, p2_in)
            if not is_entry_horizontal:
                return four_seg(p1_out, p2_in) if entry_conflict_v else self._vhv(p1_out, p2_in)
            return self._vhv(p1_out, p2_in)
    
    def _vhv(self, p1, p2):
        """
        Vertical → Horizontal → Vertical
        """
        mid_y = (p1.y() + p2.y()) / 2
        return [
            QPointF(p1.x(), mid_y),
            QPointF(p2.x(), mid_y)
        ]


    def _hvh(self, p1, p2):
        """
        Horizontal → Vertical → Horizontal
        """
        mid_x = (p1.x() + p2.x()) / 2
        return [
            QPointF(mid_x, p1.y()),
            QPointF(mid_x, p2.y())
        ]
    
    def _hvhv(self, p1, p2):
        """
        Horizontal → Vertical → Horizontal → Vertical
        """
        mid_x = (p1.x() + p2.x()) / 2
        mid_y = (p1.y() + p2.y()) / 2
        return [
            QPointF(mid_x, p1.y()),
            QPointF(mid_x, mid_y),
            QPointF(p2.x(), mid_y),
        ]


    def _vhvh(self, p1, p2):
        """
        Vertical → Horizontal → Vertical → Horizontal
        """
        mid_x = (p1.x() + p2.x()) / 2
        mid_y = (p1.y() + p2.y()) / 2
        return [
            QPointF(p1.x(), mid_y),
            QPointF(mid_x, mid_y),
            QPointF(mid_x, p2.y()),
        ]

    def _get_exit_direction(self):
        """Mantém compatibilidade com código existente"""
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

    def update_temp_endpoint(self, scene_pos):
        """Atualiza endpoint temporário garantindo atualização correta da área"""
        self.prepareGeometryChange()
        self.temp_target_pos = scene_pos
        self.update()

    def update_position(self):
        if getattr(self, '_being_deleted', False):
            return
        """Chamado quando nós conectados se movem"""
        self.prepareGeometryChange()
        self.update()

    # =========================================================================
    # Waypoints — pontos livres em coordenadas de cena
    # =========================================================================
    # Cada waypoint é um QPointF livre. O _build_ortho_points faz Ls entre eles.
    # Hover mostra losango vermelho. Drag cria/move. Duplo-clique remove.
    # =========================================================================

    _WP_HIT_RADIUS  = 10  # px — raio de snap/hover
    _WP_HOVER_RANGE = 20  # px — range de detecção de hover (maior que hit radius)
    _SEG_HIT_DIST   = 8   # px — distância para detectar clique em segmento
    _DRAG_THRESHOLD = 4   # px — mínimo de movimento para criar waypoint por drag

    @staticmethod
    def _dist_point_to_seg(px, py, ax, ay, bx, by) -> float:
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return ((px-ax)**2 + (py-ay)**2) ** 0.5
        t = max(0.0, min(1.0, ((px-ax)*dx + (py-ay)*dy) / (dx*dx+dy*dy)))
        return ((px-ax-t*dx)**2 + (py-ay-t*dy)**2) ** 0.5

    def _wp_index_at(self, scene_pos: QPointF, radius: int | None = None) -> int | None:
        """Índice do waypoint mais próximo dentro do raio dado, ou None."""
        r = radius if radius is not None else self._WP_HIT_RADIUS
        r2 = r ** 2
        best, best_i = r2, None
        for i, wp in enumerate(self.waypoints):
            d2 = (scene_pos.x()-wp.x())**2 + (scene_pos.y()-wp.y())**2
            if d2 < best:
                best, best_i = d2, i
        return best_i

    def _seg_hit_at(self, scene_pos: QPointF):
        """
        Segmento interno mais próximo dentro de _SEG_HIT_DIST.
        Retorna (insert_index, a, b) onde a e b são os extremos do segmento, ou None.
        """
        pts = self.get_path_points()
        if len(pts) < 2:
            return None
        px, py = scene_pos.x(), scene_pos.y()
        inner = pts[1:-1]  # exclui stubs source/target
        best_d, result = self._SEG_HIT_DIST + 1, None
        for i in range(len(inner) - 1):
            a, b = inner[i], inner[i+1]
            d = self._dist_point_to_seg(px, py, a.x(), a.y(), b.x(), b.y())
            if d < best_d:
                best_d = d
                result = (i, QPointF(a), QPointF(b))
        return result

    def _build_ortho_points(self, p1_out: QPointF, p2_in: QPointF,
                            exit_dir: str, entry_dir: str) -> list[QPointF]:
        """
        Conecta p1_out → waypoints → p2_in mantendo ortogonalidade.
        Se dois pontos consecutivos já estão alinhados (H ou V), conecta direto.
        Se estão desalinhados (diagonal), insere um corner para fazer o L.
        O corner é escolhido para ser consistente com a direção de chegada.
        """
        if not self.waypoints:
            return self._route_between_points(p1_out, p2_in, exit_dir, entry_dir)

        result = []
        all_pts = [p1_out] + self.waypoints + [p2_in]

        for i in range(len(all_pts) - 1):
            a = all_pts[i]
            b = all_pts[i + 1]
            already_h = abs(a.y() - b.y()) < 0.5
            already_v = abs(a.x() - b.x()) < 0.5

            if already_h or already_v:
                # já ortogonal — conecta direto
                result.append(b)
            else:
                # diagonal — precisa de corner
                # olha de onde viemos para decidir a direção do L
                if i == 0:
                    prefer_h = exit_dir in ("left", "right")
                else:
                    prev = all_pts[i - 1]
                    came_h = abs(prev.y() - a.y()) < 0.5
                    prefer_h = not came_h  # alterna: se veio H, faz V primeiro

                if prefer_h:
                    result.append(QPointF(b.x(), a.y()))
                else:
                    result.append(QPointF(a.x(), b.y()))
                result.append(b)

        return result

    def _reset_drag_state(self):
        self._drag_mode = None
        self._drag_wp_index = None
        self._drag_is_horizontal = True
        self._drag_original_wps = []
        self._pending_seg_hit = None
        self._pending_press_pos = QPointF()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._reset_drag_state()
        sp = event.scenePos()

        idx = self._wp_index_at(sp)
        if idx is not None:
            self._drag_mode = 'waypoint'
            self._drag_wp_index = idx
            self._drag_original_wps = [QPointF(p) for p in self.waypoints]
            event.accept()
            return

        hit = self._seg_hit_at(sp)
        if hit is not None:
            self._drag_mode = 'pending'
            self._pending_seg_hit = hit
            self._pending_press_pos = sp
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        sp = event.scenePos()

        # ── Drag de waypoint individual ──────────────────────────────────
        if self._drag_mode == 'waypoint':
            i = self._drag_wp_index
            if i is not None and 0 <= i < len(self._drag_original_wps):
                # Trabalha sempre a partir do snapshot original
                wps = [QPointF(p) for p in self._drag_original_wps]
                orig = wps[i]
                wps[i] = sp

                # Vizinho anterior alinhado H → move junto em Y
                if i > 0:
                    nb = wps[i-1]
                    if abs(nb.y() - orig.y()) < 0.5:
                        wps[i-1] = QPointF(nb.x(), sp.y())

                # Vizinho posterior alinhado H → move junto em Y
                if i < len(wps) - 1:
                    nb = wps[i+1]
                    if abs(nb.y() - orig.y()) < 0.5:
                        wps[i+1] = QPointF(nb.x(), sp.y())

                # Vizinho anterior alinhado V → move junto em X
                if i > 0:
                    nb = wps[i-1]
                    if abs(nb.x() - orig.x()) < 0.5:
                        wps[i-1] = QPointF(sp.x(), nb.y())

                # Vizinho posterior alinhado V → move junto em X
                if i < len(wps) - 1:
                    nb = wps[i+1]
                    if abs(nb.x() - orig.x()) < 0.5:
                        wps[i+1] = QPointF(sp.x(), nb.y())

                self.waypoints = wps
                self._hovered_wp = i
                self.prepareGeometryChange()
                self.update()
            event.accept()
            return

        # ── Drag de segmento — aguarda threshold e cria 2 waypoints ──────
        if self._drag_mode == 'pending':
            delta = sp - self._pending_press_pos
            if (delta.x()**2 + delta.y()**2)**0.5 >= self._DRAG_THRESHOLD:
                ins_idx, seg_a, seg_b = self._pending_seg_hit
                self._pending_seg_hit = None
                self.prepareGeometryChange()

                is_horizontal = abs(seg_a.y() - seg_b.y()) < 1.0

                if is_horizontal:
                    # segmento horizontal → dois waypoints com Y do mouse,
                    # X fixos nas extremidades do segmento
                    wp_a = QPointF(seg_a.x(), sp.y())
                    wp_b = QPointF(seg_b.x(), sp.y())
                else:
                    # segmento vertical → dois waypoints com X do mouse,
                    # Y fixos nas extremidades do segmento
                    wp_a = QPointF(sp.x(), seg_a.y())
                    wp_b = QPointF(sp.x(), seg_b.y())

                self.waypoints.insert(ins_idx,     wp_a)
                self.waypoints.insert(ins_idx + 1, wp_b)
                # draga os dois juntos — índice do "par"
                self._drag_mode = 'segment_pair'
                self._drag_wp_index = ins_idx  # i e i+1
                self._drag_is_horizontal = is_horizontal
                self._hovered_wp = ins_idx
                self.update()
            event.accept()
            return

        # ── Drag de par de waypoints (segmento inteiro) ──────────────────
        if self._drag_mode == 'segment_pair':
            i = self._drag_wp_index
            if i is not None and i + 1 < len(self.waypoints):
                self.prepareGeometryChange()
                if self._drag_is_horizontal:
                    self.waypoints[i]   = QPointF(self.waypoints[i].x(),   sp.y())
                    self.waypoints[i+1] = QPointF(self.waypoints[i+1].x(), sp.y())
                else:
                    self.waypoints[i]   = QPointF(sp.x(), self.waypoints[i].y())
                    self.waypoints[i+1] = QPointF(sp.x(), self.waypoints[i+1].y())
                self._hovered_wp = i
                self.update()
            event.accept()
            return

        # ── Hover passivo ─────────────────────────────────────────────────
        idx = self._wp_index_at(sp)
        if idx != self._hovered_wp:
            self._hovered_wp = idx
            self.update()

        super().mouseMoveEvent(event)

    @staticmethod
    def _approx_eq(a: QPointF, b: QPointF, tol: float = 0.5) -> bool:
        return abs(a.x()-b.x()) < tol and abs(a.y()-b.y()) < tol

    def _insert_u_for_diagonals(self, p1_out: QPointF, p2_in: QPointF):
        """
        Percorre os segmentos entre p1_out → waypoints → p2_in.
        Para cada segmento diagonal (não H nem V), insere 2 waypoints
        no meio formando um U ortogonal.
        """
        all_pts = [p1_out] + self.waypoints + [p2_in]
        result = []
        changed = False

        for i in range(len(all_pts) - 1):
            a, b = all_pts[i], all_pts[i+1]
            is_h = abs(a.y() - b.y()) < 0.5
            is_v = abs(a.x() - b.x()) < 0.5

            # Só adiciona waypoints dos pontos intermediários (não p1_out nem p2_in)
            if i > 0:
                result.append(QPointF(a))

            if not is_h and not is_v:
                # Segmento diagonal — insere U no meio
                # O U vai no ponto médio do segmento
                mid_x = (a.x() + b.x()) / 2
                mid_y = (a.y() + b.y()) / 2
                # Decide orientação do U baseada no segmento: H primeiro
                result.append(QPointF(mid_x, a.y()))
                result.append(QPointF(mid_x, b.y()))
                changed = True

        if changed:
            # Adiciona último waypoint antes de p2_in se existir
            if len(all_pts) > 2:
                result.append(QPointF(all_pts[-2]))
            self.waypoints = result

    def mouseReleaseEvent(self, event):
        if self._drag_mode == 'waypoint':
            pts = self.get_path_points()
            if len(pts) >= 4:
                self.prepareGeometryChange()
                self._insert_u_for_diagonals(pts[1], pts[-2])
                self.update()

        self._reset_drag_state()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(event)
            return
        idx = self._wp_index_at(event.scenePos())
        if idx is not None and 0 <= idx < len(self.waypoints):
            self.prepareGeometryChange()
            self.waypoints.pop(idx)
            self._hovered_wp = None
            self.update()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _draw_waypoint_handles(self, painter: QPainter):
        """
        Cinza claro em todos os waypoints quando há hover próximo.
        Vermelho apenas no waypoint sendo arrastado.
        Nada visível quando o mouse não está perto.
        """
        if self._hovered_wp is None and self._drag_mode is None:
            return
        r = self._WP_HIT_RADIUS
        dragging_idx = self._drag_wp_index if self._drag_mode in ('waypoint', 'segment_pair') else None

        for i, wp in enumerate(self.waypoints):
            is_dragging = (dragging_idx is not None and
                           (i == dragging_idx or
                            (self._drag_mode == 'segment_pair' and i == dragging_idx + 1)))
            if is_dragging:
                fill   = QColor(220, 40, 40)
                border = QColor(255, 120, 120)
            elif self._hovered_wp is not None:
                fill   = QColor(200, 200, 200, 200)
                border = QColor(255, 255, 255, 220)
            else:
                continue  # sem hover e sem drag: não desenha

            painter.setPen(QPen(border, 1))
            painter.setBrush(fill)
            diamond = QPainterPath()
            diamond.moveTo(wp.x(),     wp.y() - r)
            diamond.lineTo(wp.x() + r, wp.y())
            diamond.lineTo(wp.x(),     wp.y() + r)
            diamond.lineTo(wp.x() - r, wp.y())
            diamond.closeSubpath()
            painter.drawPath(diamond)

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

    def paint(self, painter: QPainter, option, widget=None):
        points = self.get_path_points()
        if len(points) < 2:
            return

        if self.isSelected():
            pen = QPen(Qt.GlobalColor.blue, 3)
        else:
            if self.domain == "pneumatic" and self.state == 1:
                pen = QPen(Qt.GlobalColor.green, 3)
            elif self.domain == "electric" and self.state == 1:
                pen = QPen(Qt.GlobalColor.yellow, 3)
            elif self.domain == "hydraulic":
                if self.state == "ERR":
                    pen = QPen(Qt.GlobalColor.red, 3)
                elif self.state == "PRESSURIZING":
                    pen = QPen(QColor(255, 140, 0), 3)
                elif self.state > 0:
                    pen = QPen(Qt.GlobalColor.blue, 3)
                elif self.state < 0:
                    pen = QPen(QColor(100, 180, 255), 3)
                else:
                    pen = QPen(Qt.GlobalColor.cyan, 3)
            else:
                pen = self.pen

        painter.setPen(pen)
        for start, end in zip(points, points[1:]):
            painter.drawLine(start, end)

        # Losangos dos waypoints — sempre visíveis quando há waypoints
        if self.waypoints:
            self._draw_waypoint_handles(painter)

        if self.domain == "hydraulic" and self.state != "ERR" and not self.isSelected():
            if len(points) >= 3:
                arrow_offset = 4

                flow_a = getattr(self.source_anchor, "flow", 0.0)
                if not isinstance(flow_a, str) and abs(flow_a) > 1e-10:
                    p1_out = points[1]
                    exit_dir = self._get_exit_direction()
                    p1_arrow = self._apply_margin(p1_out, exit_dir, -arrow_offset)
                    self._draw_arrow_at(painter, p1_arrow, exit_dir, flow_a, pen)

                if self.target_anchor:
                    flow_b = getattr(self.target_anchor, "flow", 0.0)
                    if not isinstance(flow_b, str) and abs(flow_b) > 1e-10:
                        p2_in = points[-2]
                        is_internal = self.source_anchor.node == self.target_anchor.node
                        exit_key = "internal" if is_internal else "external"
                        entry_dirs = self.target_anchor.exit_directions.get(exit_key, ["left"])
                        entry_dir = self._choose_best_exit_direction(points[-1], points[0], entry_dirs)
                        p2_arrow = self._apply_margin(p2_in, entry_dir, -arrow_offset)
                        self._draw_arrow_at(painter, p2_arrow, entry_dir, flow_b, pen)

    def itemChange(self, change, value):
        """Detecta mudanças e força atualização adequada"""
        if getattr(self, '_being_deleted', False):
            return value
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            # Quando seleção muda, apenas repinta com a cor correta
            self.update()
        
        return super().itemChange(change, value)

    def prepare_delete(self):
        self._being_deleted = True  # Flag para evitar loops de atualização durante deleção

        self.hide()

        # desconecta dos nodes (lógico)
        if self.source and self in self.source.connections:
            self.source.connections.remove(self)

        if self.target and self in self.target.connections:
            self.target.connections.remove(self)

        self.source = None
        self.target = None


        self.prepareGeometryChange()

    def to_dict(self):
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
        conn._waypoints_initialized = True  # não sobrescreve waypoints carregados

        source_node.connections.append(conn)
        target_node.connections.append(conn)
        return conn
    

    def set_state(self, value: float):
        """
        Atualiza o estado da connection e repinta de acordo com domínio.
        """
        if self.state != value:
            self.state = value
            self.update()

    def reset_visual_state(self):
        """Retorna a connection ao estado neutro fora de simulação"""
        self.state = 0
        self.update()