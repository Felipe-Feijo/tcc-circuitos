"""Item gráfico de conexão entre dois âncoras do diagrama."""

from PyQt6.QtWidgets import QGraphicsItem, QMenu
from PyQt6.QtGui import QColor, QPainterPath, QPen, QPainter, QPainterPathStroker, QPolygonF, QBrush, QAction
from PyQt6.QtCore import Qt, QPointF, QRectF
from graphics.items.base.diagram_item_base import DiagramItemBase

# Vetores unitários por direção — compartilhado entre _apply_margin e _draw_arrow_at.
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
    _OUTLINE_WIDTH  = 8     # levemente maior que _ACTIVE_WIDTH — sobra um contorno fino
    _OUTLINE_ALPHA  = 140

    def _is_active(self) -> bool:
        """Conexão carregando fluxo/sinal no momento — mesma condição que
        `_get_pen` já usa para escolher a cor "ativa" de cada domínio."""
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
        """Contorno fino atrás da linha principal, mesma cor do pen, pra
        reforçar visualmente que a conexão está ativa na simulação.

        Desenhado como um único QPainterPath (em vez de uma drawLine por
        segmento) pra que cada canto tenha um join só — segmentos separados
        com RoundCap se sobrepõem nas juntas e, por serem semi-transparentes,
        empilham alpha e viram bolhas mais opacas exatamente nos waypoints.
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
        # Preto no tema claro, branco no escuro — contraste garantido contra
        # qualquer cor de estado hidráulico (azul, ciano, laranja...),
        # independente da cor da linha em si.
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
        # entry_dir é sempre derivado dos exit_directions reais do anchor — nunca
        # inferido a partir do vetor até o waypoint, pois isso falha com waypoints
        # corrompidos ou com a margem diferente do A* (EXIT_PX=40px vs 6-18px do editor).
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
        """Direção de saída do source anchor em direção ao target."""
        _, _, _, _, exit_dir, _ = self._compute_exit_entry()
        return exit_dir

    def _compute_exit_entry(self):
        """Retorna (p1, p2, p1_out, p2_in, exit_dir, entry_dir) para os anchors atuais."""
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
        """Sequência completa de pontos pra cálculo de vizinhança/colinearidade,
        incluindo os pontos de margem do anchor como entradas 'ancoradas'.

        Ancorado = sempre recalculado a partir da posição atual do anchor (por
        isso já acompanha o componente ao mover, de graça); nunca é alvo de
        arrasto direto nem aparece como handle; nunca é deletável. Fonte única
        de verdade sobre "quem é vizinho de quem" -- usada tanto pelo drag de
        waypoint quanto pelo reajuste de borda após mover um nó.

        `wps` permite calcular contra uma lista de waypoints explícita (ex.
        um snapshot congelado durante um drag) em vez de `self.waypoints`.
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
            # Escolhe hvhv ou vhvh dependendo do quadrante relativo.
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

    # Primitivas de roteamento ortogonal (nomes = sequência de segmentos H/V).
    def _vhv(self, p1, p2):
        mid_y = (p1.y() + p2.y()) / 2
        return [QPointF(p1.x(), mid_y), QPointF(p2.x(), mid_y)]

    def _hvh(self, p1, p2):
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
        """Realinha o trecho de borda do lado que mudou de posição.

        Delega para `_adjust_boundary()`, que distingue um ponto solto
        redundante (deve acompanhar a borda) de um canto deliberado do
        usuário que só coincide de eixo com a borda por acaso (deve virar
        uma ponte nova, preservando o resto do desvio intocado) -- ver
        `_adjust_boundary` para os detalhes do algoritmo.

        Caso especial: quando TODOS os waypoints são colineares entre si
        no eixo compartilhado por exit_dir/entry_dir (ambos H ou ambos V —
        um único waypoint compartilhando as duas bordas é o caso mais
        comum, mas uma dobra deliberada de 2+ waypoints nesse mesmo eixo
        cai na mesma armadilha), os dois deslocamentos abaixo reivindicam
        o array inteiro e o segundo sobrescreve o primeiro por completo,
        colapsando a dobra num único segmento diagonal (achado testando a
        UI real com um Z horizontal-vertical-horizontal entre dois anchors
        que saem na vertical — os 2 waypoints do meio, colineares em x,
        eram "engolidos" pelo lado do source e depois pelo lado do
        target). Nenhuma combinação de deslocamento individual resolve
        isso; rerroteia esse trecho, como já fazíamos para n==1.
        """
        if getattr(self, '_being_deleted', False) or not self._waypoints_initialized:
            return
        if not self._anchors_in_scene() or not self.waypoints:
            return

        _, _, p1_out, p2_in, exit_dir, entry_dir = self._compute_exit_entry()
        exit_h, entry_h = exit_dir in ("left", "right"), entry_dir in ("left", "right")
        wps = self.waypoints
        n   = len(wps)

        # Rota ainda "intocada" (pristine): se os waypoints atuais batem
        # exatamente com o que `_route_between_points` geraria a partir da
        # última posição validada dos anchors (`_last_p1_out`/`_last_p2_in`
        # + direções cacheadas), então ninguém nunca arrastou/inseriu/editou
        # nada aqui -- é uma rota puramente automática (hvh/vhv/hvhv/vhvh).
        # `_adjust_boundary` não tem como saber isso: seu único sinal é
        # "`w` estava alinhado com o anchor" (`was_aligned`), o que é falso
        # por construção pro ponto de offset intermediário de um hvhv/vhvh
        # (ele fica no meio do caminho, nunca em cima do anchor) -- sem essa
        # checagem, uma rota automática de 3 pontos ganha uma ponte espúria
        # ao mover, em vez de simplesmente re-rotear (que é sempre seguro
        # aqui, já que não existe desvio manual pra preservar).
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
            # Mantém a checagem "pristine" acima válida em movimentos
            # seguintes: sem isso, `_last_exit_dir`/`_last_entry_dir`
            # ficariam presos na direção de antes do PRIMEIRO move desta
            # conexão (só `get_path_points()`/`_reroute_waypoints()`
            # atualizavam esses dois campos).
            self._last_exit_dir  = exit_dir
            self._last_entry_dir = entry_dir
        self.update()

    def _adjust_boundary(self, step: int, anchor_pt: QPointF,
                          old_anchor_pt: 'QPointF | None', is_horizontal: bool) -> None:
        """Realinha o(s) waypoint(s) perto da borda que se moveu.

        step: +1 para o lado source (caminha wps[0], wps[1], ...), -1 para
        o lado target (caminha wps[-1], wps[-2], ...).
        anchor_pt: posição atual (pós-movimento) do ponto de margem do anchor.
        old_anchor_pt: cache da posição do anchor na última vez que a
        geometria foi validada (None se nunca validada -- trata como "sem
        histórico", nunca assume redundância).
        is_horizontal: eixo travado é Y (True) ou X (False).

        Caminha da borda pra dentro. Em cada waypoint `w`:
          - Sem vizinho interno (fim da lista): gruda `w` no anchor, para.
          - `w` não compartilha o eixo travado com o vizinho interno `w2`:
            gruda só `w`, para (sem conflito -- caso comum de rota
            automática, w2 e o resto ficam intocados).
          - `w` compartilha o eixo travado com `w2` E `w` já estava
            alinhado com `old_anchor_pt` nesse eixo (ponto solto
            redundante, ex.: inserido por duplo-clique numa reta): gruda
            `w`, continua para `w2` usando a posição ANTIGA de `w` como
            nova referência (a reta continua).
          - `w` compartilha o eixo travado com `w2` mas NÃO estava
            alinhado com `old_anchor_pt` (canto deliberado do usuário --
            ex.: um desvio manual que termina nesse eixo por coincidência):
            não toca em `w` nem em nada depois dele. Insere um waypoint
            "ponte" entre `w` e o anchor -- eixo travado batendo com o
            anchor, outro eixo batendo com `w` -- exatamente o que um
            usuário faria manualmente pra resolver esse conflito.
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
    _CLICK_EPSILON     = 2.0   # px -- abaixo disso, press+release conta como clique, não drag

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

    # =========================================================================
    # Waypoints — drawing
    # =========================================================================

    def _draw_waypoint_handles(self, painter: QPainter):
        if self._hovered_wp is None and self._drag_mode is None and self._selected_wp is None:
            return
        r              = self._WP_HIT_RADIUS
        dragging_idx   = self._drag_wp_index if self._drag_mode is not None else None
        hover_wp       = self._hovered_wp
        visible_range2 = self._WP_VISIBLE_RANGE ** 2

        # Ponto de referência para o range de visibilidade dos handles.
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

    def _reroute_waypoints(self):
        """Descarta os waypoints atuais e recalcula a rota do zero."""
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
        """Insere um waypoint no segmento mais próximo; retorna o índice ou None."""
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
                fi   = i + 1  # desloca pro índice em `full`, que tem p1_out na ponta
                orig = full[fi]
                prev_h = abs(full[fi-1].y() - orig.y()) < 0.5
                prev_v = abs(full[fi-1].x() - orig.x()) < 0.5
                next_h = abs(full[fi+1].y() - orig.y()) < 0.5
                next_v = abs(full[fi+1].x() - orig.x()) < 0.5
                # full[0]/full[-1] são os pontos de margem do anchor (p1_out/p2_in),
                # não waypoints -- eles nunca se movem pra acompanhar o arrasto. Por
                # isso, quando o vizinho em questão É o anchor (fi-1 == 0 ou
                # fi+1 == len(full)-1), um eixo "batendo" tem que TRAVAR esse eixo
                # (senão o segmento até o anchor vira diagonal, já que não há como
                # compensar movendo o outro lado). Quando o vizinho é um waypoint de
                # verdade, o eixo batendo LIBERA o movimento nesse eixo, porque o
                # bloco de escrita abaixo arrasta o vizinho junto pra manter o
                # segmento ortogonal.
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
        """Remove waypoints redundantes após drag de segmento (3 pontos colineares)."""
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
        # Não chama adjust_waypoints_for_node_move()/_adjust_boundary() aqui:
        # um drag de segmento move as cópias inseridas de seg_a/seg_b juntas
        # (mousePressEvent/mouseMoveEvent acima), preservando a ortogonalidade
        # da borda por construção -- não há reparo de borda a fazer.
        self.update()

    def _undo_segment_split(self):
        """Desfaz o split temporário de segmento quando o press+release não
        teve deslocamento real -- ou seja, foi um clique de seleção, não um
        drag. Remove os 2 waypoints inseridos em mousePressEvent e pronto:
        não passa por adjust_waypoints_for_node_move, então uma conexão com
        rota não-trivial (ex. vinda de um gerador) não corre o risco de ser
        substituída pelo roteamento heurístico padrão só por ter sido clicada.
        """
        i = self._drag_wp_index
        if i is not None and 0 <= i + 1 < len(self.waypoints):
            self.prepareGeometryChange()
            self.waypoints.pop(i + 1)
            self.waypoints.pop(i)
            self.update()

    def mouseDoubleClickEvent(self, event):
        """Double-click num segmento insere um waypoint naquela posição."""
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
        action = QAction("Deletar waypoint", menu)
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
                # Sincroniza com o tema atual: o item pode ter sido criado
                # depois do último toggle, sem nunca ter recebido o sinal.
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
        self.source = self.target = None
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
        # Semeia o cache de posição/direção dos anchors com os valores atuais
        # (== os valores no momento do save, já que os anchors não se moveram
        # desde então) ANTES da repara abaixo. Sem isso, `_last_p1_out`/
        # `_last_p2_in`/`_last_exit_dir`/`_last_entry_dir` ficam nos defaults
        # de `__init__` e a checagem "rota pristina" de
        # `adjust_waypoints_for_node_move` nunca dispara aqui -- qualquer rota
        # automática de 3+ pontos (hvhv/vhvh) carregada do arquivo ganha uma
        # ponte espúria (zero-length, sentada em cima do próprio anchor) só
        # por essa falta de histórico, e essa ponte é persistida de volta no
        # próximo save.
        if conn._anchors_in_scene():
            _, _, p1_out, p2_in, exit_dir, entry_dir = conn._compute_exit_entry()
            conn._last_p1_out, conn._last_p2_in = QPointF(p1_out), QPointF(p2_in)
            conn._last_exit_dir, conn._last_entry_dir = exit_dir, entry_dir
        # Repara waypoints não-ortogonais salvos por versões antigas.
        # Seguro para waypoints do A* pois o sanity check é apenas wp→wp.
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