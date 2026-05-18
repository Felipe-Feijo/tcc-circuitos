"""
A* orthogonal router para circuitos pneumáticos estáticos.

Princípios de design:
  1. O A* roteia entre dois pontos FORA dos sprites (exit points)
  2. Os waypoints gerados são APENAS os pontos de dobra intermediários
     (não incluem src_anchor nem tgt_anchor)
  3. O primeiro wp é "snapped" à coordenada exata do src_anchor na direção perpendicular
  4. O último wp é "snapped" à coordenada exata do tgt_anchor na direção perpendicular
  5. Exhaust/PS nunca precisam de waypoints (sempre linhas retas)
"""

from __future__ import annotations
import heapq
import math

CELL      = 20    # pixels por célula
EXIT_PX   = 40    # pixels de saída antes do A* (2 células)
TURN_COST = 8     # custo por mudança de direção
WIRE_COST = 3     # custo por passar sobre fio existente

DIRS = [(0, -1), (0, 1), (-1, 0), (1, 0)]   # UP DOWN LEFT RIGHT

SPRITE_SIZES: dict[str, tuple[int, int]] = {
    "Valve_4_2_Ways":        (447, 180),
    "Valve_5_2_Ways":        (650, 180),
    "Valve_3_2_Ways":        (444, 180),
    "DoubleActingCylinder":  (498, 193),
    "PressureLine":          (71,  12),
    "Exhaust":               (33,  33),
    "PressureSource":        (29,  29),
}

# Direção de saída padrão de cada anchor
EXIT_DIR_MAP: dict[tuple[str, str], str] = {
    ("DoubleActingCylinder", "A"):  "DOWN",
    ("DoubleActingCylinder", "B"):  "DOWN",
    ("Valve_4_2_Ways",      "A"):   "UP",
    ("Valve_4_2_Ways",      "B"):   "UP",
    ("Valve_5_2_Ways",      "A"):   "UP",
    ("Valve_5_2_Ways",      "B"):   "UP",
    ("Valve_3_2_Ways",      "A"):   "UP",
    ("Exhaust",              "R"):  "UP",
    ("PressureSource",       "P"):  "UP",
    ("Valve_3_2_Ways",      "P"):   "DOWN",
    ("Valve_3_2_Ways",      "R"):   "DOWN",
    ("Valve_4_2_Ways",      "P"):   "DOWN",
    ("Valve_4_2_Ways",      "R"):   "DOWN",
    ("Valve_5_2_Ways",      "P"):   "DOWN",
    ("Valve_5_2_Ways",      "R1"):  "DOWN",
    ("Valve_5_2_Ways",      "R2"):  "DOWN",
    ("Valve_4_2_Ways",      "PL"):  "LEFT",
    ("Valve_5_2_Ways",      "PL"):  "LEFT",
    ("Valve_4_2_Ways",      "PR"):  "RIGHT",
    ("Valve_5_2_Ways",      "PR"):  "RIGHT",
}

DIR_VEC = {"UP": (0,-1), "DOWN": (0,1), "LEFT": (-1,0), "RIGHT": (1,0)}


def get_exit_dir(node_type: str, anchor: str) -> str:
    key = (node_type, anchor)
    if key in EXIT_DIR_MAP:
        return EXIT_DIR_MAP[key]
    if node_type == "PressureLine" and anchor.startswith("X"):
        return "UP"
    return "UP"


# ── Grid ──────────────────────────────────────────────────────────────────────
class Grid:
    def __init__(self, x_min: float, y_min: float, x_max: float, y_max: float):
        pad = EXIT_PX * 4
        self.ox = int(x_min) - pad
        self.oy = int(y_min) - pad
        self.cols = int((x_max - x_min + pad * 2) / CELL) + 2
        self.rows = int((y_max - y_min + pad * 2) / CELL) + 2
        self._obs:  list[float] = [0.0] * (self.cols * self.rows)
        self._wire: list[float] = [0.0] * (self.cols * self.rows)

    def px_to_cell(self, px: float, py: float) -> tuple[int, int]:
        return (int((px - self.ox) / CELL), int((py - self.oy) / CELL))

    # Converter célula → pixel usando a grade (não o centro)
    # O snap vai ajustar para o valor exato depois
    def cell_to_px(self, cx: int, cy: int) -> tuple[float, float]:
        return (self.ox + cx * CELL, self.oy + cy * CELL)

    def _idx(self, cx: int, cy: int) -> int:
        return cy * self.cols + cx

    def in_bounds(self, cx: int, cy: int) -> bool:
        return 0 <= cx < self.cols and 0 <= cy < self.rows

    def cost(self, cx: int, cy: int) -> float:
        if not self.in_bounds(cx, cy):
            return math.inf
        idx = self._idx(cx, cy)
        o = self._obs[idx]
        if o >= 1e6:
            return math.inf
        return o + self._wire[idx]

    def block_rect_px(self, x0: float, y0: float, x1: float, y1: float):
        """Bloqueia retângulo definido por cantos (x0,y0)→(x1,y1) em pixels."""
        cx0, cy0 = self.px_to_cell(x0, y0)
        cx1, cy1 = self.px_to_cell(x1, y1)
        for cy in range(max(0, cy0), min(self.rows, cy1 + 1)):
            for cx in range(max(0, cx0), min(self.cols, cx1 + 1)):
                self._obs[self._idx(cx, cy)] = math.inf

    def mark_wire(self, path_cells: list[tuple[int, int]]):
        for cx, cy in path_cells:
            if self.in_bounds(cx, cy):
                self._wire[self._idx(cx, cy)] += WIRE_COST


# Guarda posição/tamanho de cada nó para calcular exits fora do bloco
_NODE_BOUNDS: dict[str, tuple[float,float,float,float]] = {}  # id→(x,y,w,h)

def build_grid(nodes: list[dict]) -> Grid:
    global _NODE_BOUNDS
    _NODE_BOUNDS = {}

    xs, ys = [], []
    for n in nodes:
        px, py = n["position"]["x"], n["position"]["y"]
        w, h = SPRITE_SIZES.get(n["type"], (50, 50))
        xs += [px, px + w]; ys += [py, py + h]

    grid = Grid(min(xs), min(ys), max(xs), max(ys))

    VALVE_TYPES = {"Valve_4_2_Ways", "Valve_5_2_Ways", "Valve_3_2_Ways"}
    CYL_TYPES   = {"DoubleActingCylinder"}
    SMALL_OBS   = {"Exhaust", "PressureSource"}  # pequenos obstáculos sem margem
    SKIP_TYPES  = {"PressureLine"}                # PLs não bloqueiam
    MH = 80   # margem horizontal para válvulas

    for n in nodes:
        t = n["type"]
        px, py = n["position"]["x"], n["position"]["y"]
        w, h = SPRITE_SIZES.get(t, (50, 50))

        if t in SKIP_TYPES:
            _NODE_BOUNDS[n["id"]] = (px, py, w, h)
            continue

        if t in SMALL_OBS:
            # PS e Exhaust: obstáculos sem margem (são pequenos)
            grid.block_rect_px(px, py, px + w, py + h)
            _NODE_BOUNDS[n["id"]] = (px, py, w, h)
            continue

        if t in VALVE_TYPES:
            grid.block_rect_px(px - MH, py, px + w + MH, py + h)
            _NODE_BOUNDS[n["id"]] = (px - MH, py, w + 2*MH, h)
        elif t in CYL_TYPES:
            mh = 30
            grid.block_rect_px(px - mh, py, px + w + mh, py + h)
            _NODE_BOUNDS[n["id"]] = (px - mh, py, w + 2*mh, h)
        else:
            grid.block_rect_px(px, py, px + w, py + h)
            _NODE_BOUNDS[n["id"]] = (px, py, w, h)

    return grid


# ── A* ────────────────────────────────────────────────────────────────────────
def _astar(
    grid: Grid,
    sx: int, sy: int,
    ex: int, ey: int,
    init_dir_idx: int,
) -> list[tuple[int, int]] | None:
    INF = math.inf

    def h(cx, cy):
        return abs(cx - ex) + abs(cy - ey)

    dist: dict = {(sx, sy, init_dir_idx): 0.0}
    prev: dict = {}
    pq = [(h(sx, sy), 0.0, sx, sy, init_dir_idx)]

    while pq:
        _, g, cx, cy, d = heapq.heappop(pq)
        if dist.get((cx, cy, d), INF) < g - 1e-9:
            continue
        if cx == ex and cy == ey:
            path = []
            state = (cx, cy, d)
            while state in prev:
                path.append((state[0], state[1]))
                state = prev[state]
            path.append((state[0], state[1]))
            path.reverse()
            return path

        for ni, (dcx, dcy) in enumerate(DIRS):
            nx, ny = cx + dcx, cy + dcy
            c = grid.cost(nx, ny)
            if c >= 1e6:
                continue
            turn = 0 if ni == d else TURN_COST
            ng = g + 1.0 + c + turn
            ns = (nx, ny, ni)
            if ng < dist.get(ns, INF):
                dist[ns] = ng
                prev[ns] = (cx, cy, d)
                heapq.heappush(pq, (ng + h(nx, ny), ng, nx, ny, ni))
    return None


def _find_free_exit(grid: Grid, ax: int, ay: int, ddx: int, ddy: int, steps: int = 15) -> tuple[int,int] | None:
    """Encontra a primeira célula livre saindo de (ax,ay) na direção (ddx,ddy)."""
    for i in range(0, steps + 1):
        nx, ny = ax + ddx * i, ay + ddy * i
        if grid.in_bounds(nx, ny) and grid.cost(nx, ny) < 1e6:
            return (nx, ny)
    return None


def _exit_point_for_anchor(
    grid: Grid,
    node_id: str,
    anchor_px: tuple[float, float],
    dir_: str,
) -> tuple[int, int] | None:
    """
    Calcula o exit point correto para um anchor com saída lateral (LEFT/RIGHT).
    Para anchors RIGHT/LEFT que ficam DENTRO do sprite, o exit deve estar
    imediatamente além da borda do bloco de obstáculos.
    Para anchors UP/DOWN (nas bordas H do sprite), usa _find_free_exit normal.
    """
    ddx, ddy = DIR_VEC[dir_]
    ax, ay = grid.px_to_cell(*anchor_px)

    if dir_ in ("UP", "DOWN"):
        # Anchor na borda superior/inferior — exit está próximo
        return _find_free_exit(grid, ax, ay, ddx, ddy)

    # Anchor lateral (LEFT/RIGHT) — pode estar dentro do bloco
    # Calcular a borda do bloco e ir para além dela
    bounds = _NODE_BOUNDS.get(node_id)
    if bounds is not None:
        bx, by, bw, bh = bounds
        if dir_ == "RIGHT":
            # Sair pela direita: exit.x > bx + bw
            exit_px_x = bx + bw + CELL
            exit_px_y = anchor_px[1]
        else:
            # Sair pela esquerda: exit.x < bx
            exit_px_x = bx - CELL
            exit_px_y = anchor_px[1]
        ex, ey = grid.px_to_cell(exit_px_x, exit_px_y)
        # Verificar se está livre, senão buscar próxima livre
        for extra in range(0, 5):
            nx, ny = ex + ddx * extra, ey
            if grid.in_bounds(nx, ny) and grid.cost(nx, ny) < 1e6:
                return (nx, ny)

    # Fallback
    return _find_free_exit(grid, ax, ay, ddx, ddy)


def route_connection(
    grid: Grid,
    src_px: tuple[float, float], src_dir: str,
    tgt_px: tuple[float, float], tgt_dir: str,
    src_type: str = "", tgt_type: str = "",
    src_id: str = "", tgt_id: str = "",
) -> list[dict] | None:
    """
    Roteia ortogonalmente de src_px a tgt_px.
    Retorna lista de waypoints intermediários (sem src nem tgt).
    None = linha reta (sem waypoints necessários).
    """
    # Exhaust/PS: sempre linha reta
    if src_type in ("Exhaust", "PressureSource") or tgt_type in ("Exhaust", "PressureSource"):
        return None

    # Conexão já reta?
    if abs(src_px[0] - tgt_px[0]) < 3 or abs(src_px[1] - tgt_px[1]) < 3:
        return None

    # ── PL → pilot (PL/PR de v42 ou mc): rota determinística de 2 segmentos ──
    # A rota é sempre: subir/descer até o y do pilot → ir horizontal até o pilot.
    # Não usa A* (que causa "rabinhos" de ~10px no final).
    # Só se aplica quando src é PressureLine e tgt sai para LEFT ou RIGHT.
    if src_type == "PressureLine" and tgt_dir in ("LEFT", "RIGHT"):
        # Subir/descer da PL até a altura do pilot, depois ir horizontal
        # wp1: mesmo x da PL, y do pilot  → segmento vertical PL→pilot_height
        # wp2: mesmo y do pilot, x do pilot → segmento horizontal até o pilot
        # (o editor conecta: PL_anchor → wp1 → wp2 → pilot_anchor)
        # wp1 só é necessário se PL.y ≠ pilot.y (sempre, pois PL está abaixo do v42)
        return [
            {"x": round(src_px[0], 1), "y": round(tgt_px[1], 1)},
            {"x": round(tgt_px[0], 1), "y": round(tgt_px[1], 1)},
        ]

    # ── Direção de saída contextual ───────────────────────────────────────────
    # Para anchors verticais (UP/DOWN), usar a direção que aponta PARA o destino.
    # Para PressureLine (src ou tgt), a direção nominal é sempre "UP" (emissão),
    # mas o roteamento precisa da direção CONTEXTUAL (em relação ao destino).
    dy_total = tgt_px[1] - src_px[1]   # + = tgt abaixo, - = tgt acima
    dx_total = tgt_px[0] - src_px[0]

    sdx, sdy = DIR_VEC[src_dir]
    tdx, tdy = DIR_VEC[tgt_dir]

    # FIX Bug 2 (rabinhos): src_dir corrigido ANTES de calcular o exit point,
    # para que exit point e direção inicial do A* sempre concordem.
    #
    # Anchors UP/DOWN: apontar para o destino contextualmente.
    # PressureLine como src: idem — seu anchor Xi é nominal UP mas deve rotear
    # para baixo quando o destino está abaixo.
    if src_dir in ("UP", "DOWN") or src_type == "PressureLine":
        sdy = 1 if dy_total >= 0 else -1
        sdx = 0

    # FIX (loops/voltas): quando tgt_dir aponta na mesma direção que a viagem
    # src→tgt, o exit point fica ALÉM do anchor (o A* ultrapassa o destino e
    # tem que voltar), gerando as "voltas por cima/baixo".
    #
    # Regra: o exit point do TARGET deve estar do lado de ONDE A CONEXÃO CHEGA.
    # Se a rota viaja verticalmente (tdx==0), o exit deve estar oposto à viagem:
    #   viaja DOWN (dy>0) mas tgt_dir=DOWN → exit além → corrigir: tdy=UP (-1)
    #   viaja UP   (dy<0) mas tgt_dir=UP   → exit além → corrigir: tdy=DOWN (+1)
    # Isso era aplicado só para PressureLine; agora generalizado para qualquer target.
    if tdx == 0:  # anchor vertical (UP ou DOWN)
        if dy_total > 0 and tdy > 0:   # viajando DOWN, tgt sai DOWN → exit está abaixo: corrigir para UP
            tdy = -1
        elif dy_total < 0 and tdy < 0: # viajando UP, tgt sai UP → exit está acima: corrigir para DOWN
            tdy = 1
    elif tdy == 0:  # anchor horizontal (LEFT ou RIGHT)
        if dx_total > 0 and tdx > 0:   # viajando RIGHT, tgt sai RIGHT → exit à direita: corrigir para LEFT
            tdx = -1
        elif dx_total < 0 and tdx < 0: # viajando LEFT, tgt sai LEFT → exit à esquerda: corrigir para RIGHT
            tdx = 1

    # Guardar direções finais para passar ao _exit_point_for_anchor
    src_dir_used = {(0,-1):"UP",(0,1):"DOWN",(-1,0):"LEFT",(1,0):"RIGHT"}.get((sdx,sdy), src_dir)
    tgt_dir_used = {(0,-1):"UP",(0,1):"DOWN",(-1,0):"LEFT",(1,0):"RIGHT"}.get((tdx,tdy), tgt_dir)

    # ── Células dos anchors ───────────────────────────────────────────────────
    sx_c, sy_c = grid.px_to_cell(src_px[0], src_px[1])
    tx_c, ty_c = grid.px_to_cell(tgt_px[0], tgt_px[1])

    # Calcular exit points usando borda do bloco (não o anchor em si).
    # Para PressureLine como src: _find_free_exit retorna i=0 (própria célula,
    # pois PL não tem bloco de obstáculo). Isso faz o exit point ficar na célula
    # de grade arredondada (≠ anchor real), causando um mini-segmento "rabinho"
    # antes do A* virar na direção correta. Fix: forçar EXIT_PX na direção correta.
    if src_type == "PressureLine":
        ddx, ddy = DIR_VEC[src_dir_used]
        ax, ay = grid.px_to_cell(src_px[0], src_px[1])
        # Avançar ao menos 1 célula além do anchor para garantir saída limpa
        steps = max(1, EXIT_PX // CELL)
        s_exit = None
        for i in range(1, steps + 3):
            nx, ny = ax + ddx * i, ay + ddy * i
            if grid.in_bounds(nx, ny) and grid.cost(nx, ny) < 1e6:
                s_exit = (nx, ny)
                break
        if s_exit is None:
            s_exit = _exit_point_for_anchor(grid, src_id, src_px, src_dir_used)
    else:
        s_exit = _exit_point_for_anchor(grid, src_id, src_px, src_dir_used)
    t_exit = _exit_point_for_anchor(grid, tgt_id, tgt_px, tgt_dir_used)

    if s_exit is None or t_exit is None:
        return None

    # Para chegada vertical (tdx=0): forçar t_exit.x = anchor.x (mesma coluna)
    # Para chegada horizontal (tdy=0): forçar t_exit.y = anchor.y (mesma linha)
    if tgt_type == "PressureLine":
        # PL não tem bloco — chegar na mesma coluna do anchor com o y calculado
        # pelo _exit_point_for_anchor (que já usou tgt_dir_used contextual).
        t_exit = (tx_c, t_exit[1])
        # Fallback: se a célula estiver bloqueada, usar direto o anchor
        if not grid.in_bounds(t_exit[0], t_exit[1]) or grid.cost(t_exit[0], t_exit[1]) >= 1e6:
            t_exit = (tx_c, ty_c)
    elif tdx == 0:
        t_exit = (tx_c, t_exit[1])
        if not grid.in_bounds(t_exit[0], t_exit[1]) or grid.cost(t_exit[0], t_exit[1]) >= 1e6:
            for extra in range(1, 10):
                ny = ty_c + tdy * extra
                if grid.in_bounds(tx_c, ny) and grid.cost(tx_c, ny) < 1e6:
                    t_exit = (tx_c, ny); break
            else:
                return None
    else:
        t_exit = (t_exit[0], ty_c)
        if not grid.in_bounds(t_exit[0], t_exit[1]) or grid.cost(t_exit[0], t_exit[1]) >= 1e6:
            for extra in range(1, 10):
                nx = tx_c + tdx * extra
                if grid.in_bounds(nx, ty_c) and grid.cost(nx, ty_c) < 1e6:
                    t_exit = (nx, ty_c); break
            else:
                return None

    # ── Rodar A* ─────────────────────────────────────────────────────────────
    init_dir_idx = DIRS.index((sdx, sdy))
    cells = _astar(grid, s_exit[0], s_exit[1], t_exit[0], t_exit[1], init_dir_idx)
    if cells is None:
        return None

    # Simplificar: remover colineares
    def simplify(pts):
        if len(pts) < 3:
            return pts
        out = [pts[0]]
        for i in range(1, len(pts) - 1):
            px_,py_ = pts[i-1]; cx_,cy_ = pts[i]; nx_,ny_ = pts[i+1]
            if (cx_-px_ == nx_-cx_) and (cy_-py_ == ny_-cy_):
                continue
            out.append((cx_, cy_))
        out.append(pts[-1])
        return out

    cells = simplify(cells)
    grid.mark_wire(cells)

    # ── Converter células para pixels com snap de ortogonalidade ────────────
    # Estratégia:
    #   1. Converter cada célula para px (grid alinhado)
    #   2. Propagar src.x (se saída vertical) para todos os pontos do trecho
    #      inicial que ficam na mesma coluna x → garante src→wp0 seja vertical
    #   3. Idem para chegada no tgt
    #   4. Verificar cada segmento; se diagonal, inserir ponto de dobra

    wps_px = [grid.cell_to_px(cx, cy) for cx, cy in cells]
    if not wps_px:
        return None

    # Snap inicial: propagar coordenada do src para o trecho de saída.
    #
    # CAUSA RAIZ DO RABINHO: para saída vertical (sdx==0), o snap propaga
    # src_px[0] (x) corretamente, mas o y do primeiro ponto fica em
    # grid.cell_to_px(s_exit).y — um múltiplo de CELL, não src_px[1].
    # Isso cria um mini-segmento src(y_anchor) → wp0(y_grade) na direção
    # errada antes de o A* virar. Fix: após propagar x, também fixar
    # o y do primeiro ponto (e de todos que estejam na mesma coluna que
    # o src) para src_px[1].  Idem para saída horizontal com src_px[1]/[0].
    if sdx == 0:  # saída vertical → fixar x = src.x; y do primeiro pt = src.y
        ref_x = wps_px[0][0]
        first_in_col = True
        for i in range(len(wps_px)):
            if abs(wps_px[i][0] - ref_x) < CELL:
                if first_in_col:
                    # Primeiro ponto na coluna de saída: fixar AMBOS x e y ao anchor
                    wps_px[i] = (src_px[0], src_px[1])
                    first_in_col = False
                else:
                    wps_px[i] = (src_px[0], wps_px[i][1])
            else:
                break
    else:  # saída horizontal → fixar y = src.y; x do primeiro pt = src.x
        ref_y = wps_px[0][1]
        first_in_row = True
        for i in range(len(wps_px)):
            if abs(wps_px[i][1] - ref_y) < CELL:
                if first_in_row:
                    wps_px[i] = (src_px[0], src_px[1])
                    first_in_row = False
                else:
                    wps_px[i] = (wps_px[i][0], src_px[1])
            else:
                break

    # Snap final: propagar coordenada do tgt para o trecho de chegada.
    # Mesma lógica: o último ponto na coluna/linha de chegada é fixado
    # com AMBAS as coordenadas do anchor de destino.
    if tdx == 0:  # chegada vertical → fixar x = tgt.x; y do último pt = tgt.y
        ref_x = wps_px[-1][0]
        last_in_col = True
        for i in range(len(wps_px)-1, -1, -1):
            if abs(wps_px[i][0] - ref_x) < CELL:
                if last_in_col:
                    wps_px[i] = (tgt_px[0], tgt_px[1])
                    last_in_col = False
                else:
                    wps_px[i] = (tgt_px[0], wps_px[i][1])
            else:
                break
    else:  # chegada horizontal → fixar y = tgt.y; x do último pt = tgt.x
        ref_y = wps_px[-1][1]
        last_in_row = True
        for i in range(len(wps_px)-1, -1, -1):
            if abs(wps_px[i][1] - ref_y) < CELL:
                if last_in_row:
                    wps_px[i] = (tgt_px[0], tgt_px[1])
                    last_in_row = False
                else:
                    wps_px[i] = (wps_px[i][0], tgt_px[1])
            else:
                break

    # Garantir ortogonalidade em cada segmento:
    # src → wp[0] → wp[1] → ... → wp[N] → tgt
    def enforce_ortho(all_pts):
        """Garante que todos os segmentos são H ou V, inserindo pontos de dobra se necessário."""
        out = [all_pts[0]]
        for pt in all_pts[1:]:
            px_, py_ = out[-1]
            cx_, cy_ = pt
            dx_, dy_ = abs(cx_ - px_), abs(cy_ - py_)
            if dx_ < 2 or dy_ < 2:
                # Ortogonal — snap para alinhar exatamente
                if dx_ < dy_:
                    out.append((px_, cy_))   # mesma x que anterior
                else:
                    out.append((cx_, py_))   # mesmo y que anterior
            else:
                # Diagonal — inserir ponto de dobra (H depois V)
                out.append((px_, cy_))   # dobra na y do próximo, mantendo x do atual
                out.append((cx_, cy_))
        return out

    all_pts = [src_px] + wps_px + [tgt_px]
    fixed = enforce_ortho(all_pts)

    # Extrair apenas os intermediários (sem src e tgt) e remover:
    # - duplicados consecutivos (distância < 2px)
    # - pontos coincidentes com src ou tgt (gerados pelo snap duplo)
    interior = fixed[1:-1]
    clean = []
    for px, py in interior:
        # Pular se igual ao src
        if abs(px - src_px[0]) < 2 and abs(py - src_px[1]) < 2:
            continue
        # Pular se igual ao tgt
        if abs(px - tgt_px[0]) < 2 and abs(py - tgt_px[1]) < 2:
            continue
        # Pular se duplicado do anterior
        if clean and abs(px - clean[-1]["x"]) < 2 and abs(py - clean[-1]["y"]) < 2:
            continue
        clean.append({"x": round(px, 1), "y": round(py, 1)})

    # Simplificar: remover pontos colineares com seus vizinhos
    def _simplify_wps(pts, s, t):
        all_ = [s] + [(p["x"], p["y"]) for p in pts] + [t]
        out = [all_[0]]
        for i in range(1, len(all_) - 1):
            px_, py_ = out[-1]; cx_, cy_ = all_[i]; nx_, ny_ = all_[i+1]
            same_col = abs(cx_ - px_) < 2 and abs(nx_ - cx_) < 2
            same_row = abs(cy_ - py_) < 2 and abs(ny_ - cy_) < 2
            if same_col or same_row:
                continue  # ponto colinear — remover
            out.append((cx_, cy_))
        out.append(all_[-1])
        return [{"x": round(p[0],1), "y": round(p[1],1)} for p in out[1:-1]]

    clean = _simplify_wps(clean, src_px, tgt_px)
    return clean if clean else None