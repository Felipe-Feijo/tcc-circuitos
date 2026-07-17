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

from circuit_generator.sprite_metrics import METRICS as _M, anchor_local_for_routing

CELL      = 20    # pixels por célula
EXIT_PX   = 40    # pixels de saída antes do A* (2 células)
TURN_COST = 8     # custo por mudança de direção
WIRE_COST = 3     # custo por passar sobre fio existente

DIRS = [(0, -1), (0, 1), (-1, 0), (1, 0)]   # UP DOWN LEFT RIGHT

# Fonte única de verdade: sprite_metrics.py (lê os PNGs reais). Antes, estes
# valores eram hardcoded aqui separadamente e haviam ficado desatualizados
# (ex: Valve_4_2_Ways com 447px em vez dos 300px reais) -- o retângulo de
# bloqueio de colisão do A* ficava maior que o sprite de verdade, e um
# anchor legitimamente posicionado logo além da borda real (ex: PR, que
# sprite_metrics.py posiciona em v42_width + pilot_w) caía "dentro" desse
# bloqueio inflado, forçando o roteador a escapar bem mais longe do que
# necessário e depois saltar de volta -- ver
# tests/test_astar_router.py::TestSpriteSizesMatchMetrics.
SPRITE_SIZES: dict[str, tuple[int, int]] = {
    "Valve_4_2_Ways":        (_M.v42_width, _M.v42_height),
    "Valve_5_2_Ways":        (_M.v52_width, _M.v52_height),
    "Valve_3_2_Ways":        (_M.v32_width, _M.v32_height),
    "DoubleActingCylinder":  (_M.cyl_width, _M.cyl_height),
    "PressureLine":          (_M.pl_pix_w,  _M.pl_pix_h),
    "Exhaust":               (_M.exh_width, _M.exh_height),
    "PressureSource":        (_M.ps_width,  _M.ps_height),
    "OrValve":               (_M.or_width,  _M.or_height),
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
    ("OrValve",              "X"):  "LEFT",
    ("OrValve",              "Y"):  "RIGHT",
    ("OrValve",              "A"):  "UP",
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

VALVE_TYPES = {"Valve_4_2_Ways", "Valve_5_2_Ways", "Valve_3_2_Ways"}


def _commutation_shift(n: dict) -> float:
    """Deslocamento horizontal REAL do sprite de uma válvula direcional
    quando renderizada no estado comutado (body_state=1, default_side ==
    "left" -- ver graphics/items/base/nodes/directional_valve/
    directional_valve_item.py: `self.body_state = 1 if default_side ==
    "left" else 0`, e cada Valve_*_ways.py's BODY_VISUALS[1]["offset"]).
    0.0 pra qualquer outro tipo ou estado -- o sprite nunca desloca pra
    esquerda, só pra direita, então isso é sempre o pior caso (mais à
    direita) que o corpo pode realmente ocupar.

    Sem isso, build_grid() bloqueava o retângulo de colisão na posição
    LÓGICA (não-deslocada) da válvula -- quando ela estava no estado
    comutado, o sprite de verdade renderizava mais à direita do que o
    retângulo de bloqueio previa, e um fio podia entrar "por dentro" do
    corpo real mesmo o A* achando aquele trecho livre (achado testando a
    UI real: conexão sig.A -> mem.PR cruzando o corpo de uma memória
    comutada).
    """
    if n["type"] not in VALVE_TYPES:
        return 0.0
    if n.get("properties", {}).get("default_side") != "left":
        return 0.0
    return _M.pilot_side_offset_x.get(n["type"], 0.0)


def build_grid(nodes: list[dict]) -> Grid:
    global _NODE_BOUNDS
    _NODE_BOUNDS = {}

    # Os limites do grid precisam alcançar qualquer anchor real que o
    # roteamento vá mirar -- não só o tamanho bruto do sprite. PL/PR de
    # válvulas direcionais protudem além do sprite (anchor_local_for_routing
    # já embute a margem de comutação pro pior caso de PR, ver Task 1) --
    # sem isso, um anchor de válvula perto da borda do circuito cai fora
    # do grid e o roteamento falha silenciosamente (route_connection
    # devolve None). Ver docs/superpowers/specs/
    # 2026-07-11-directional-valve-pilot-anchor-offset-design.md.
    xs, ys = [], []
    for n in nodes:
        px, py = n["position"]["x"], n["position"]["y"]
        px += _commutation_shift(n)
        t = n["type"]
        w, h = SPRITE_SIZES.get(t, (50, 50))
        xs += [px, px + w]; ys += [py, py + h]
        for anchor_name in ("PL", "PR"):
            local = anchor_local_for_routing(t, anchor_name)
            if local:
                xs.append(px + local[0])
                ys.append(py + local[1])

    grid = Grid(min(xs), min(ys), max(xs), max(ys))

    CYL_TYPES   = {"DoubleActingCylinder"}
    SMALL_OBS   = {"Exhaust", "PressureSource"}  # pequenos obstáculos sem margem
    SKIP_TYPES  = {"PressureLine"}                # PLs não bloqueiam
    OR_TYPES    = {"OrValve"}
    MH = 80   # margem horizontal para válvulas
    # Margem vertical só pra OrValve -- feedback direto testando a UI
    # real: sem nenhuma margem (caía no ramo genérico, bloqueio exato do
    # sprite), um fio podia passar rente por cima/embaixo da OrValve. X/Y
    # (esquerda/direita) já têm folga própria via _find_free_exit e não
    # precisam de margem horizontal aqui.
    MV_OR = 20

    for n in nodes:
        t = n["type"]
        px, py = n["position"]["x"], n["position"]["y"]
        px += _commutation_shift(n)
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
        elif t in OR_TYPES:
            grid.block_rect_px(px, py - MV_OR, px + w, py + h + MV_OR)
            _NODE_BOUNDS[n["id"]] = (px, py - MV_OR, w, h + 2*MV_OR)
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

    # ── Offset unificado na direção de entrada do target ─────────────────────
    # O editor aplica um margin de 6-18px na saída/entrada de cada anchor.
    # Nos blocos determinísticos, empurramos o último wp 20px além do anchor
    # na direção de entrada, para o fio chegar limpo sem rabinho.
    _OFFSET = 20
    _OFF = {
        "UP":    ( 0, -_OFFSET),
        "DOWN":  ( 0, +_OFFSET),
        "LEFT":  (-_OFFSET,  0),
        "RIGHT": (+_OFFSET,  0),
    }

    def src_off(d):
        dx, dy = _OFF[d]
        return (round(src_px[0] + dx, 1), round(src_px[1] + dy, 1))

    def tgt_off(d):
        dx, dy = _OFF[d]
        return (round(tgt_px[0] + dx, 1), round(tgt_px[1] + dy, 1))

    def wp(x, y): return {"x": round(x, 1), "y": round(y, 1)}

    # ── pilot (PL/PR) → PressureLine ─────────────────────────────────────────
    # Sai horizontal do pilot → desce/sobe até y da PL → entra na PL.
    if src_dir in ("LEFT", "RIGHT") and tgt_type == "PressureLine":
        return [
            wp(tgt_px[0], src_px[1]),
        ]

    # ── PressureLine → Valve_3_2_Ways.P (sig.P) ──────────────────────────────
    # anchor P fica na base (DOWN). Chega por baixo com offset.
    if src_type == "PressureLine" and tgt_type == "Valve_3_2_Ways" and tgt_dir == "DOWN":
        ox, oy = tgt_off("DOWN")
        return [
            wp(src_px[0], oy),
            wp(tgt_px[0], oy),
        ]

    # ── Valve_4_2_Ways.A/B → DoubleActingCylinder ────────────────────────────
    # A/B saem UP do topo da v42, pistão recebe DOWN na base.
    # Chega no pistão por baixo com offset.
    if src_type == "Valve_4_2_Ways" and tgt_type == "DoubleActingCylinder":
        ox, oy = tgt_off("DOWN")
        return [
            wp(src_px[0], oy),
            wp(tgt_px[0], oy),
        ]

    # ── Valve_5_2_Ways.A/B → PressureLine ────────────────────────────────────
    # Sobe do anchor UP da 5/2, vai horizontal até x da PL, desce até PL.
    if src_type == "Valve_5_2_Ways" and tgt_type == "PressureLine":
        ox, oy = src_off("UP")
        return [
            wp(src_px[0], oy),
            wp(tgt_px[0], oy),
        ]

    # ── PressureLine → Valve_5_2_Ways ────────────────────────────────────────
    if src_type == "PressureLine" and tgt_type == "Valve_5_2_Ways":
        ox, oy = tgt_off("UP")
        return [
            wp(src_px[0], oy),
            wp(tgt_px[0], oy),
        ]

    # ── OrValve.A → OrValve.X/Y (elo de cadeia multi-ciclo) ──────────────────
    # A fica sempre no topo (exit "UP"). Sem este atalho, a A* geral às
    # vezes prefere contornar por BAIXO das duas válvulas (passando pela
    # folga entre or_row e a região de lógica, mais larga que a folga
    # entre or_row e main_valve) -- confirmado pelo usuário, que pediu
    # explicitamente pra passar por CIMA.
    #
    # PRECISA de um 3º waypoint que já pouse no Y real do alvo (tgt_px[1])
    # ANTES do ponto final -- X/Y só aceitam entrada horizontal (exit_dir
    # "left"/"right", ver or_valve.py), e connection_item.py
    # (adjust_waypoints_for_node_move -> _shift_collinear_run) corrige
    # automaticamente qualquer sequência de waypoints COLINEARES adjacente
    # à borda do alvo pra bater com o Y real dele. Com só 2 waypoints (os
    # dois na mesma altura "oy", ver versão anterior deste atalho), os DOIS
    # compartilham o mesmo Y e a correção colapsa a ponte inteira pro Y do
    # alvo -- destruindo a subida por cima (confirmado pelo usuário
    # revendo o resultado: o fio ainda descia reto pelo meio). Com 3
    # pontos, só o último (já no Y do alvo) é tocado -- os dois primeiros
    # (na altura "oy", diferente) ficam fora da corrida colinear e
    # preservam a ponte.
    if src_type == "OrValve" and tgt_type == "OrValve":
        ox, oy = src_off("UP")
        tox, toy = tgt_off(tgt_dir)
        return [
            wp(src_px[0], oy),
            wp(tox, oy),
            wp(tox, toy),
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

    # FIX Bug 1 (loops na PL): quando PressureLine é TARGET, o exit point de
    # chegada deve estar do lado de onde a conexão vem, não no lado de emissão.
    # tgt_dir_used controla onde _find_free_exit posiciona o exit point:
    #   src ABAIXO da PL (dy_total < 0) → viaja UP → exit point ABAIXO da PL → DOWN (+1)
    #   src ACIMA  da PL (dy_total > 0) → viaja DOWN → exit point ACIMA da PL → UP  (-1)
    if tgt_type == "PressureLine":
        tdy = 1 if dy_total <= 0 else -1
        tdx = 0

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
    # FIX Bug PressureLine como TARGET:
    # _find_free_exit começa em i=0 (própria célula) e como a PL está em SKIP_TYPES
    # (sem bloco de obstáculo), retorna imediatamente o próprio anchor, ignorando
    # tgt_dir_used. O A* sempre termina no topo da PL.
    # Fix: calcular t_exit avançando explicitamente na direção correta, igual ao
    # tratamento de PressureLine como src.
    if tgt_type == "PressureLine":
        ddx_t, ddy_t = DIR_VEC[tgt_dir_used]
        # tgt_dir_used já foi calculado (bloco "FIX Bug 1" acima) para
        # apontar pro lado de onde a conexão VEM, não pro lado de emissão:
        #   src ABAIXO da PL (dy_total <= 0) → tgt_dir_used="DOWN" (ddy_t=+1)
        #   src ACIMA  da PL (dy_total > 0)  → tgt_dir_used="UP"   (ddy_t=-1)
        # O exit point (onde o A* termina antes do hop final até o anchor
        # real) precisa ficar do MESMO lado -- por isso usa ddy_t direto,
        # sem inverter. Uma versão anterior deste bloco invertia o sinal
        # (opp_ddy = -ddy_t) por engano -- o comentário daquela versão
        # descrevia a convenção OPOSTA da que o bloco "FIX Bug 1" realmente
        # usa, colocando o exit point do lado ERRADO da PL: o fio cruzava
        # a linha inteira e voltava (ver
        # tests/test_step_by_step_layout.py::TestComponentToPressureLineDoesNotCrossThrough).
        t_exit = None
        steps = max(1, EXIT_PX // CELL)
        for i in range(1, steps + 3):
            nx, ny = tx_c + 0 * i, ty_c + ddy_t * i
            if grid.in_bounds(nx, ny) and grid.cost(nx, ny) < 1e6:
                t_exit = (tx_c, ny)
                break
        if t_exit is None:
            t_exit = (tx_c, ty_c)  # fallback: próprio anchor
    else:
        t_exit = _exit_point_for_anchor(grid, tgt_id, tgt_px, tgt_dir_used)

    if s_exit is None or t_exit is None:
        return None

    # Para chegada vertical (tdx=0): forçar t_exit.x = anchor.x (mesma coluna)
    # Para chegada horizontal (tdy=0): forçar t_exit.y = anchor.y (mesma linha)
    if tgt_type == "PressureLine":
        pass  # t_exit já calculado acima com x=tx_c e y correto
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

    # Snap inicial: propagar coordenada do src para o trecho de saída
    if sdx == 0:  # saída vertical → fixar x = src.x em todos os pts iniciais mesma coluna
        ref_x = wps_px[0][0]
        for i in range(len(wps_px)):
            if abs(wps_px[i][0] - ref_x) < CELL:
                wps_px[i] = (src_px[0], wps_px[i][1])
            else:
                break
    else:  # saída horizontal → fixar y = src.y
        ref_y = wps_px[0][1]
        for i in range(len(wps_px)):
            if abs(wps_px[i][1] - ref_y) < CELL:
                wps_px[i] = (wps_px[i][0], src_px[1])
            else:
                break

    # Snap final: propagar coordenada do tgt para o trecho de chegada
    if tdx == 0:  # chegada vertical → fixar x = tgt.x
        ref_x = wps_px[-1][0]
        for i in range(len(wps_px)-1, -1, -1):
            if abs(wps_px[i][0] - ref_x) < CELL:
                wps_px[i] = (tgt_px[0], wps_px[i][1])
            else:
                break
    else:  # chegada horizontal → fixar y = tgt.y
        ref_y = wps_px[-1][1]
        for i in range(len(wps_px)-1, -1, -1):
            if abs(wps_px[i][1] - ref_y) < CELL:
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

    # Extrair apenas os intermediários (sem src e tgt) e remover duplicados
    interior = fixed[1:-1]
    clean = []
    for px, py in interior:
        if clean and abs(px - clean[-1]["x"]) < 2 and abs(py - clean[-1]["y"]) < 2:
            continue
        clean.append({"x": round(px, 1), "y": round(py, 1)})

    return clean if clean else None