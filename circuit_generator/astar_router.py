"""
A* orthogonal router for static pneumatic circuits.

Design principles:
  1. A* routes between two points OUTSIDE the sprites (exit points)
  2. The generated waypoints are ONLY the intermediate bend points
     (don't include src_anchor or tgt_anchor)
  3. The first wp is "snapped" to src_anchor's exact coordinate on the perpendicular axis
  4. The last wp is "snapped" to tgt_anchor's exact coordinate on the perpendicular axis
  5. Exhaust/PS never need waypoints (always straight lines)
"""

from __future__ import annotations
import heapq
import math

from circuit_generator.sprite_metrics import METRICS as _M, anchor_local_for_routing

CELL      = 20    # pixels per cell
EXIT_PX   = 40    # exit pixels before A* runs (2 cells)
TURN_COST = 8     # cost per direction change
WIRE_COST = 3     # cost per pass over an existing wire

DIRS = [(0, -1), (0, 1), (-1, 0), (1, 0)]   # UP DOWN LEFT RIGHT

# Single source of truth: sprite_metrics.py (reads the real PNGs). These
# values used to be hardcoded here separately and had drifted out of
# date (e.g. Valve_4_2_Ways at 447px instead of the real 300px) -- A*'s
# collision-blocking rectangle ended up bigger than the real sprite, and
# an anchor legitimately positioned just past the real edge (e.g. PR,
# which sprite_metrics.py places at v42_width + pilot_w) fell "inside"
# that inflated block, forcing the router to escape much further than
# necessary and then jump back -- see
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
    "RelaySwitch":           (_M.relay_switch_width,  _M.relay_switch_height),
    "SolenoidCoil":          (_M.solenoid_coil_width, _M.solenoid_coil_height),
    "RelayCoil":             (_M.relay_coil_width,    _M.relay_coil_height),
    "ButtonSwitch":          (_M.button_switch_width, _M.button_switch_height),
    "VoltageSource":         (_M.vsource_pix_w,       _M.vsource_pix_h),
    "Ground":                (_M.ground_pix_w,        _M.ground_pix_h),
}

# Each anchor's default exit direction
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
    ("RelaySwitch",          "T"):  "UP",
    ("RelaySwitch",          "B"):  "DOWN",
    ("SolenoidCoil",         "T"):  "UP",
    ("SolenoidCoil",         "B"):  "DOWN",
    ("RelayCoil",            "T"):  "UP",
    ("RelayCoil",            "B"):  "DOWN",
    ("ButtonSwitch",         "T"):  "UP",
    ("ButtonSwitch",         "B"):  "DOWN",
}

DIR_VEC = {"UP": (0,-1), "DOWN": (0,1), "LEFT": (-1,0), "RIGHT": (1,0)}


def get_exit_dir(node_type: str, anchor: str) -> str:
    key = (node_type, anchor)
    if key in EXIT_DIR_MAP:
        return EXIT_DIR_MAP[key]
    if node_type == "PressureLine" and anchor.startswith("X"):
        return "UP"
    if node_type == "VoltageSource" and anchor.startswith("X"):
        return "DOWN"
    if node_type == "Ground" and anchor.startswith("X"):
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

    # Convert cell -> pixel using the grid (not the center)
    # The snap step adjusts to the exact value afterward
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
        """Blocks the rectangle defined by corners (x0,y0)->(x1,y1) in pixels."""
        cx0, cy0 = self.px_to_cell(x0, y0)
        cx1, cy1 = self.px_to_cell(x1, y1)
        for cy in range(max(0, cy0), min(self.rows, cy1 + 1)):
            for cx in range(max(0, cx0), min(self.cols, cx1 + 1)):
                self._obs[self._idx(cx, cy)] = math.inf

    def mark_wire(self, path_cells: list[tuple[int, int]]):
        for cx, cy in path_cells:
            if self.in_bounds(cx, cy):
                self._wire[self._idx(cx, cy)] += WIRE_COST


# Stores each node's position/size, to compute exits outside its block
_NODE_BOUNDS: dict[str, tuple[float,float,float,float]] = {}  # id→(x,y,w,h)

VALVE_TYPES = {"Valve_4_2_Ways", "Valve_5_2_Ways", "Valve_3_2_Ways"}


def _commutation_shift(n: dict) -> float:
    """A directional valve sprite's REAL horizontal shift when rendered
    in the commutated state (body_state=1, default_side == "left" -- see
    graphics/items/base/nodes/directional_valve/directional_valve_item.py:
    `self.body_state = 1 if default_side == "left" else 0`, and each
    Valve_*_ways.py's BODY_VISUALS[1]["offset"]). 0.0 for any other type
    or state -- the sprite never shifts left, only right, so this is
    always the worst case (furthest right) the body can actually occupy.

    Without this, build_grid() blocked the collision rectangle at the
    valve's LOGICAL (unshifted) position -- when it was in the
    commutated state, the real sprite rendered further right than the
    blocking rectangle predicted, and a wire could enter "inside" the
    real body even though A* thought that stretch was clear (found via
    live-UI testing: a sig.A -> mem.PR connection crossing a commutated
    memory's body).
    """
    if n["type"] not in VALVE_TYPES:
        return 0.0
    if n.get("properties", {}).get("default_side") != "left":
        return 0.0
    return _M.pilot_side_offset_x.get(n["type"], 0.0)


def build_grid(nodes: list[dict]) -> Grid:
    global _NODE_BOUNDS
    _NODE_BOUNDS = {}

    # The grid's bounds need to reach every real anchor routing might
    # target -- not just the sprite's raw size. Directional valves' PL/PR
    # protrude past the sprite (anchor_local_for_routing already bakes in
    # the worst-case commutation margin for PR, see Task 1) -- without
    # this, a valve anchor near the circuit's edge falls outside the grid
    # and routing silently fails (route_connection returns None). See
    # docs/superpowers/specs/
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
    SMALL_OBS   = {"Exhaust", "PressureSource"}  # small obstacles, no margin
    SKIP_TYPES  = {"PressureLine"}                # PLs don't block
    OR_TYPES    = {"OrValve"}
    MH = 80   # horizontal margin for valves
    # Vertical margin, OrValve only -- found via live-UI testing: with no
    # margin at all (falling into the generic branch, exact sprite
    # blocking), a wire could graze right past the OrValve's top/bottom.
    # X/Y (left/right) already have their own clearance via
    # _find_free_exit and don't need a horizontal margin here.
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
            # PS and Exhaust: obstacles with no margin (they're small)
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
    """Finds the first free cell going out from (ax,ay) in direction (ddx,ddy)."""
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
    Computes the correct exit point for an anchor with a sideways exit
    (LEFT/RIGHT). For RIGHT/LEFT anchors that sit INSIDE the sprite, the
    exit must be immediately past the obstacle block's edge.
    For UP/DOWN anchors (on the sprite's H edges), uses the normal
    _find_free_exit.
    """
    ddx, ddy = DIR_VEC[dir_]
    ax, ay = grid.px_to_cell(*anchor_px)

    if dir_ in ("UP", "DOWN"):
        # Anchor on the top/bottom edge -- exit is nearby
        return _find_free_exit(grid, ax, ay, ddx, ddy)

    # Sideways anchor (LEFT/RIGHT) -- may be inside the block
    # Compute the block's edge and go past it
    bounds = _NODE_BOUNDS.get(node_id)
    if bounds is not None:
        bx, by, bw, bh = bounds
        if dir_ == "RIGHT":
            # Exit to the right: exit.x > bx + bw
            exit_px_x = bx + bw + CELL
            exit_px_y = anchor_px[1]
        else:
            # Exit to the left: exit.x < bx
            exit_px_x = bx - CELL
            exit_px_y = anchor_px[1]
        ex, ey = grid.px_to_cell(exit_px_x, exit_px_y)
        # Check whether it's free, otherwise look for the next free one
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
    Routes orthogonally from src_px to tgt_px.
    Returns a list of intermediate waypoints (without src or tgt).
    None = straight line (no waypoints needed).
    """
    # Exhaust/PS: always a straight line
    if src_type in ("Exhaust", "PressureSource") or tgt_type in ("Exhaust", "PressureSource"):
        return None

    # Already a straight connection?
    if abs(src_px[0] - tgt_px[0]) < 3 or abs(src_px[1] - tgt_px[1]) < 3:
        return None

    # -- Unified offset in the target's entry direction ------------------------
    # The editor applies a 6-18px margin on each anchor's exit/entry. In
    # the deterministic blocks, we push the last wp 20px past the anchor
    # in the entry direction, so the wire arrives clean, no little tail.
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

    # -- pilot (PL/PR) -> PressureLine ------------------------------------------
    # Exits the pilot horizontally -> moves down/up to the PL's y -> enters the PL.
    if src_dir in ("LEFT", "RIGHT") and tgt_type == "PressureLine":
        return [
            wp(tgt_px[0], src_px[1]),
        ]

    # -- PressureLine -> Valve_3_2_Ways.P (sig.P) --------------------------------
    # Anchor P sits at the base (DOWN). Arrives from below with an offset.
    if src_type == "PressureLine" and tgt_type == "Valve_3_2_Ways" and tgt_dir == "DOWN":
        ox, oy = tgt_off("DOWN")
        return [
            wp(src_px[0], oy),
            wp(tgt_px[0], oy),
        ]

    # -- Valve_4_2_Ways.A/B -> DoubleActingCylinder -------------------------------
    # A/B exit UP from the v42's top, the piston receives DOWN at its base.
    # Arrives at the piston from below with an offset.
    if src_type == "Valve_4_2_Ways" and tgt_type == "DoubleActingCylinder":
        ox, oy = tgt_off("DOWN")
        return [
            wp(src_px[0], oy),
            wp(tgt_px[0], oy),
        ]

    # -- Valve_5_2_Ways.A/B -> PressureLine ---------------------------------------
    # Goes up from the 5/2's UP anchor, moves horizontally to the PL's x, goes down to the PL.
    if src_type == "Valve_5_2_Ways" and tgt_type == "PressureLine":
        ox, oy = src_off("UP")
        return [
            wp(src_px[0], oy),
            wp(tgt_px[0], oy),
        ]

    # -- PressureLine -> Valve_5_2_Ways -------------------------------------------
    if src_type == "PressureLine" and tgt_type == "Valve_5_2_Ways":
        ox, oy = tgt_off("UP")
        return [
            wp(src_px[0], oy),
            wp(tgt_px[0], oy),
        ]

    # -- OrValve.A -> OrValve.X/Y (multi-cycle chain link) ------------------------
    # A always exits at the top ("UP"). Without this shortcut, general A*
    # sometimes prefers routing BELOW both valves (through the gap
    # between or_row and the logic region, wider than the gap between
    # or_row and main_valve) -- confirmed by the user, who explicitly
    # asked for it to go OVER the top instead.
    #
    # NEEDS a 3rd waypoint that already sits at the target's real Y
    # (tgt_px[1]) BEFORE the final point -- X/Y only accept horizontal
    # entry (exit_dir "left"/"right", see or_valve.py), and
    # connection_item.py (adjust_waypoints_for_node_move ->
    # _adjust_boundary) automatically fixes any run of COLLINEAR
    # waypoints adjacent to the target's boundary to match its real Y.
    # With only 2 waypoints (both at the same height "oy", see this
    # shortcut's earlier version), BOTH share the same Y and the fix
    # collapses the whole bridge to the target's Y -- destroying the
    # over-the-top route (confirmed by the user reviewing the result:
    # the wire still went straight down through the middle). With 3
    # points, only the last one (already at the target's Y) gets
    # touched -- the first two (at the different "oy" height) stay out
    # of the collinear run and preserve the bridge.
    if src_type == "OrValve" and tgt_type == "OrValve":
        ox, oy = src_off("UP")
        tox, toy = tgt_off(tgt_dir)
        return [
            wp(src_px[0], oy),
            wp(tox, oy),
            wp(tox, toy),
        ]

    # -- Contextual exit direction -----------------------------------------------
    # For vertical anchors (UP/DOWN), use the direction that points TOWARD the target.
    # For PressureLine (src or tgt), the nominal direction is always "UP" (emission),
    # but routing needs the CONTEXTUAL direction (relative to the target).
    dy_total = tgt_px[1] - src_px[1]   # + = tgt abaixo, - = tgt acima
    dx_total = tgt_px[0] - src_px[0]

    sdx, sdy = DIR_VEC[src_dir]
    tdx, tdy = DIR_VEC[tgt_dir]

    # FIX Bug 2 (little tails): src_dir corrected BEFORE computing the
    # exit point, so the exit point and A*'s initial direction always
    # agree.
    #
    # UP/DOWN anchors: point toward the target contextually.
    # PressureLine as src: same idea -- its Xi anchor is nominally UP but
    # must route downward when the target is below.
    if src_dir in ("UP", "DOWN") or src_type == "PressureLine":
        sdy = 1 if dy_total >= 0 else -1
        sdx = 0

    # FIX Bug 1 (loops on the PL): when PressureLine is the TARGET, the
    # arrival exit point must be on the side the connection comes from,
    # not the emission side. tgt_dir_used controls where _find_free_exit
    # places the exit point:
    #   src BELOW the PL (dy_total < 0) -> travels UP -> exit point BELOW the PL -> DOWN (+1)
    #   src ABOVE the PL (dy_total > 0) -> travels DOWN -> exit point ABOVE the PL -> UP  (-1)
    if tgt_type == "PressureLine":
        tdy = 1 if dy_total <= 0 else -1
        tdx = 0

    # Store the final directions to pass to _exit_point_for_anchor
    src_dir_used = {(0,-1):"UP",(0,1):"DOWN",(-1,0):"LEFT",(1,0):"RIGHT"}.get((sdx,sdy), src_dir)
    tgt_dir_used = {(0,-1):"UP",(0,1):"DOWN",(-1,0):"LEFT",(1,0):"RIGHT"}.get((tdx,tdy), tgt_dir)

    # -- Anchor cells --------------------------------------------------------------
    sx_c, sy_c = grid.px_to_cell(src_px[0], src_px[1])
    tx_c, ty_c = grid.px_to_cell(tgt_px[0], tgt_px[1])

    # Compute exit points using the block's edge (not the anchor itself).
    # For PressureLine as src: _find_free_exit returns i=0 (its own cell,
    # since PL has no obstacle block). This leaves the exit point at the
    # rounded grid cell (!= the real anchor), causing a mini "tail"
    # segment before A* turns in the right direction. Fix: force EXIT_PX
    # in the right direction.
    if src_type == "PressureLine":
        ddx, ddy = DIR_VEC[src_dir_used]
        ax, ay = grid.px_to_cell(src_px[0], src_px[1])
        # Advance at least 1 cell past the anchor to guarantee a clean exit
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
    # FIX Bug PressureLine as TARGET:
    # _find_free_exit starts at i=0 (its own cell) and since PL is in
    # SKIP_TYPES (no obstacle block), it immediately returns the anchor
    # itself, ignoring tgt_dir_used. A* always ends up at the PL's top.
    # Fix: compute t_exit by explicitly stepping in the right direction,
    # same treatment as PressureLine as src.
    if tgt_type == "PressureLine":
        ddx_t, ddy_t = DIR_VEC[tgt_dir_used]
        # tgt_dir_used was already computed (the "FIX Bug 1" block above)
        # to point at the side the connection COMES FROM, not the
        # emission side:
        #   src BELOW the PL (dy_total <= 0) -> tgt_dir_used="DOWN" (ddy_t=+1)
        #   src ABOVE the PL (dy_total > 0)  -> tgt_dir_used="UP"   (ddy_t=-1)
        # The exit point (where A* ends before the final hop to the real
        # anchor) needs to be on the SAME side -- hence using ddy_t
        # directly, without negating. An earlier version of this block
        # negated the sign (opp_ddy = -ddy_t) by mistake -- that
        # version's comment described the OPPOSITE convention from what
        # the "FIX Bug 1" block actually uses, placing the exit point on
        # the WRONG side of the PL: the wire crossed the whole line and
        # came back (see
        # tests/test_step_by_step_layout.py::TestComponentToPressureLineDoesNotCrossThrough).
        t_exit = None
        steps = max(1, EXIT_PX // CELL)
        for i in range(1, steps + 3):
            nx, ny = tx_c + 0 * i, ty_c + ddy_t * i
            if grid.in_bounds(nx, ny) and grid.cost(nx, ny) < 1e6:
                t_exit = (tx_c, ny)
                break
        if t_exit is None:
            t_exit = (tx_c, ty_c)  # fallback: the anchor itself
    else:
        t_exit = _exit_point_for_anchor(grid, tgt_id, tgt_px, tgt_dir_used)

    if s_exit is None or t_exit is None:
        return None

    # For vertical arrival (tdx=0): force t_exit.x = anchor.x (same column)
    # For horizontal arrival (tdy=0): force t_exit.y = anchor.y (same row)
    if tgt_type == "PressureLine":
        pass  # t_exit already computed above with x=tx_c and the right y
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

    # -- Run A* ----------------------------------------------------------------
    init_dir_idx = DIRS.index((sdx, sdy))
    cells = _astar(grid, s_exit[0], s_exit[1], t_exit[0], t_exit[1], init_dir_idx)
    if cells is None:
        return None

    # Simplify: remove collinear points
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

    # -- Convert cells to pixels with orthogonality snapping --------------------
    # Strategy:
    #   1. Convert each cell to px (grid-aligned)
    #   2. Propagate src.x (if exiting vertically) to every point in the
    #      initial stretch that shares the same x column -> guarantees src->wp0 is vertical
    #   3. Same for the arrival at tgt
    #   4. Check each segment; if diagonal, insert a bend point

    wps_px = [grid.cell_to_px(cx, cy) for cx, cy in cells]
    if not wps_px:
        return None

    # Initial snap: propagate the src's coordinate to the exit stretch
    if sdx == 0:  # vertical exit -> fix x = src.x on every initial point in the same column
        ref_x = wps_px[0][0]
        for i in range(len(wps_px)):
            if abs(wps_px[i][0] - ref_x) < CELL:
                wps_px[i] = (src_px[0], wps_px[i][1])
            else:
                break
    else:  # horizontal exit -> fix y = src.y
        ref_y = wps_px[0][1]
        for i in range(len(wps_px)):
            if abs(wps_px[i][1] - ref_y) < CELL:
                wps_px[i] = (wps_px[i][0], src_px[1])
            else:
                break

    # Final snap: propagate the tgt's coordinate to the arrival stretch
    if tdx == 0:  # vertical arrival -> fix x = tgt.x
        ref_x = wps_px[-1][0]
        for i in range(len(wps_px)-1, -1, -1):
            if abs(wps_px[i][0] - ref_x) < CELL:
                wps_px[i] = (tgt_px[0], wps_px[i][1])
            else:
                break
    else:  # horizontal arrival -> fix y = tgt.y
        ref_y = wps_px[-1][1]
        for i in range(len(wps_px)-1, -1, -1):
            if abs(wps_px[i][1] - ref_y) < CELL:
                wps_px[i] = (wps_px[i][0], tgt_px[1])
            else:
                break

    # Ensure orthogonality on every segment:
    # src -> wp[0] -> wp[1] -> ... -> wp[N] -> tgt
    def enforce_ortho(all_pts):
        """Ensures every segment is H or V, inserting bend points as needed."""
        out = [all_pts[0]]
        for pt in all_pts[1:]:
            px_, py_ = out[-1]
            cx_, cy_ = pt
            dx_, dy_ = abs(cx_ - px_), abs(cy_ - py_)
            if dx_ < 2 or dy_ < 2:
                # Orthogonal -- snap to align exactly
                if dx_ < dy_:
                    out.append((px_, cy_))   # same x as the previous point
                else:
                    out.append((cx_, py_))   # same y as the previous point
            else:
                # Diagonal -- insert a bend point (H then V)
                out.append((px_, cy_))   # bend at the next point's y, keeping the current x
                out.append((cx_, cy_))
        return out

    all_pts = [src_px] + wps_px + [tgt_px]
    fixed = enforce_ortho(all_pts)

    # Extract only the intermediates (without src and tgt) and dedupe
    interior = fixed[1:-1]
    clean = []
    for px, py in interior:
        if clean and abs(px - clean[-1]["x"]) < 2 and abs(py - clean[-1]["y"]) < 2:
            continue
        clean.append({"x": round(px, 1), "y": round(py, 1)})

    return clean if clean else None