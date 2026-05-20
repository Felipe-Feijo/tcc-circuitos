import json
from pathlib import Path
from circuit_generator.sprite_metrics import METRICS as _M

_CONFIG_PATH = Path(__file__).parent / "layout_config.json"

_ANCHOR_LOCAL: dict[str, dict[str, tuple[float, float]]] = _M.anchor_local

# Tipos-filho que se posicionam relativos ao pai (Exhaust/PS)
_CHILD_CONNECT_ANCHOR: dict[str, str] = {
    "Exhaust":        "R",
    "PressureSource": "P",
}


def _anchor_local(node_type: str, anchor_name: str) -> tuple[float, float] | None:
    return _ANCHOR_LOCAL.get(node_type, {}).get(anchor_name)


def _scene_x(node_id: str, anchor_name: str,
              node_pos: dict, node_type_map: dict) -> float | None:
    """Posição X em cena de um anchor de qualquer nó posicionado."""
    npos  = node_pos.get(node_id)
    ntype = node_type_map.get(node_id, "")
    if npos is None:
        return None
    if ntype == "PressureLine" and anchor_name.startswith("X"):
        idx = int(anchor_name[1:])
        return npos[0] + _M.pl_pix_w / 2 + (idx - 1) * _M.pl_spacing
    local = _anchor_local(ntype, anchor_name)
    return (npos[0] + local[0]) if local else npos[0]


def _scene_xy(node_id: str, anchor_name: str,
               node_pos: dict, node_type_map: dict) -> tuple[float, float] | None:
    """Posição (X, Y) em cena de um anchor de qualquer nó posicionado."""
    npos  = node_pos.get(node_id)
    ntype = node_type_map.get(node_id, "")
    if npos is None:
        return None
    if ntype == "PressureLine" and anchor_name.startswith("X"):
        idx = int(anchor_name[1:])
        return (npos[0] + _M.pl_pix_w / 2 + (idx - 1) * _M.pl_spacing, npos[1])
    local = _anchor_local(ntype, anchor_name)
    return (npos[0] + local[0], npos[1] + local[1]) if local else npos


# ── Helpers de anchor em PressureLine ────────────────────────────────────────

def _pl_anchor_x(pl_node: dict, anchor_name: str, node_pos: dict) -> float:
    pl_x = node_pos[pl_node["id"]][0]
    return pl_x + _M.pl_pix_w / 2 + (int(anchor_name[1:]) - 1) * _M.pl_spacing


def _nearest_pl_anchor(pl_node: dict, target_x: float, node_pos: dict,
                        side: str = "any") -> str:
    """
    Retorna o anchor Xi mais próximo de target_x.
    side='left'  → apenas anchors com x < target_x (fallback: mais à esquerda)
    side='right' → apenas anchors com x > target_x (fallback: mais à direita)
    side='any'   → o mais próximo sem restrição
    """
    anchors = pl_node["properties"]["anchors"]
    scored = [(int(n[1:]), _pl_anchor_x(pl_node, n, node_pos), n) for n in anchors]

    if side == "left":
        candidates = [(abs(ax - target_x), n) for _, ax, n in scored if ax < target_x]
        fallback   = sorted(scored)[0][2]
    elif side == "right":
        candidates = [(abs(ax - target_x), n) for _, ax, n in scored if ax > target_x]
        fallback   = sorted(scored, reverse=True)[0][2]
    else:
        candidates = [(abs(ax - target_x), n) for _, ax, n in scored]
        fallback   = anchors[0]

    return min(candidates)[1] if candidates else fallback


def _best_pl_anchor_clear_column(pl_node: dict, target_x: float,
                                   y_top: float, y_bot: float,
                                   node_pos: dict, node_type_map: dict,
                                   pl_anchor_used: dict) -> str:
    """
    Anchor cujo eixo vertical [y_top, y_bot] está mais livre de sprites.
    Critérios (prioridade): livre → não-ocupado → mais próximo de target_x.
    """
    from circuit_generator.astar_router import SPRITE_SIZES as _SS
    MH = 80
    VALVE_TYPES = {"Valve_4_2_Ways", "Valve_5_2_Ways", "Valve_3_2_Ways"}

    blocking = []
    for nid, npos in node_pos.items():
        ntype = node_type_map.get(nid, "")
        if ntype in ("PressureLine", "Exhaust", "PressureSource"):
            continue
        w, h = _SS.get(ntype, (0, 0))
        if not w:
            continue
        mg = MH if ntype in VALVE_TYPES else 30
        if npos[1] + h > y_top and npos[1] < y_bot:
            blocking.append((npos[0] - mg, npos[0] + w + mg))

    def is_clear(ax: float) -> bool:
        return all(not (bx0 <= ax <= bx1) for bx0, bx1 in blocking)

    anchors = pl_node["properties"]["anchors"]
    candidates = []
    for name in anchors:
        ax = _pl_anchor_x(pl_node, name, node_pos)
        candidates.append((not is_clear(ax), round(ax) in pl_anchor_used,
                           abs(ax - target_x), name))
    candidates.sort(key=lambda c: c[:3])
    chosen = candidates[0][3]
    pl_anchor_used[round(_pl_anchor_x(pl_node, chosen, node_pos))] = ("_clear_col", 0.0)
    return chosen


def apply(data: dict) -> dict:
    """
    Posiciona todos os nós do circuito pneumático, atribui anchors às
    PressureLines e roteia as conexões com A*.
    """
    cfg  = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    rows = cfg["rows"]
    cols = cfg["columns"]
    gap  = cfg.get("anchor_child_gap", 20)

    cyl_first_x  = cols["cylinder_first_x"]
    cyl_group_w  = cols["cylinder_group_width"]
    pl_grp_x     = cols["pl_grp_x"]
    memory_x     = cols["memory_x"]
    btn_offset_x = cols["btn_offset_x"]
    ps_offset_x  = cols["ps_offset_x"]
    step_mod_w   = cols["step_module_width"]

    # ── Mapas auxiliares ─────────────────────────────────────────────────────
    node_type_map: dict[str, str] = {n["id"]: n["type"] for n in data["nodes"]}
    role_map:      dict[str, str] = {n["id"]: n.get("_role", "") for n in data["nodes"]}

    # letter → coluna x dos cilindros
    cyl_col: dict[str, float] = {}
    for nid, role in role_map.items():
        if role.startswith("cylinder:"):
            letter = role.split(":", 1)[1]
            if letter not in cyl_col:
                cyl_col[letter] = cyl_first_x + len(cyl_col) * cyl_group_w

    node_pos: dict[str, tuple[float, float]] = {}

    # ── Varredura de conexões: montar todos os mapas de uma vez ──────────────
    child_parent:    dict[str, tuple[str, str]] = {}
    sig_to_v42:      dict[str, tuple[str, str]] = {}
    sig_to_mc:       dict[str, tuple[str, str]] = {}
    sig_to_btn:      set[str]                   = set()
    sig_to_sig:      dict[str, str]             = {}

    for conn in data.get("connections", []):
        s_id, s_anc = conn["source"]["node"], conn["source"]["anchor"]
        t_id, t_anc = conn["target"]["node"], conn["target"]["anchor"]
        s_type, t_type = node_type_map.get(s_id,""), node_type_map.get(t_id,"")
        s_role, t_role = role_map.get(s_id,""), role_map.get(t_id,"")

        # Exhaust / PS → pai
        for child, parent, p_anc in [(s_id, t_id, t_anc), (t_id, s_id, s_anc)]:
            if node_type_map.get(child) in _CHILD_CONNECT_ANCHOR:
                child_parent.setdefault(child, (parent, p_anc))

        # sig → v42 pilot
        if (s_type == "Valve_3_2_Ways" and s_anc == "A" and
                t_type == "Valve_4_2_Ways" and t_anc in ("PL", "PR")):
            sig_to_v42[s_id] = (t_id, t_anc)

        # sig → mc pilot
        if (s_type == "Valve_3_2_Ways" and s_anc == "A" and
                t_type == "Valve_5_2_Ways" and t_anc in ("PL", "PR") and
                s_role.startswith("signal_valve:")):
            sig_to_mc[s_id] = (t_id, t_anc)

        # sig → btn ou sig → sig
        if (s_type == "Valve_3_2_Ways" and s_anc == "A" and
                t_type == "Valve_3_2_Ways" and t_anc == "P" and
                s_role.startswith("signal_valve:")):
            if t_role == "button":
                sig_to_btn.add(s_id)
            else:
                sig_to_sig[s_id] = t_id

    # ── Fase 1: nós primários ─────────────────────────────────────────────────
    deferred:    list[dict] = []  # Exhaust / PS
    deferred_mc: list[dict] = []  # memórias, btn, sigs que dependem das mc

    def _place(node: dict, x: float, y: float) -> None:
        node["position"] = {"x": x, "y": y}
        node_pos[node["id"]] = (x, y)
        node.pop("_role", None)

    for node in data["nodes"]:
        role  = node.get("_role", "")
        ntype = node["type"]

        if not role:
            node.pop("_role", None)
            continue

        if ntype in _CHILD_CONNECT_ANCHOR and node["id"] in child_parent:
            deferred.append(node)
            continue

        # roles que dependem das mc posicionadas
        if (role == "button" or role.startswith("memory:") or
                (role.startswith("signal_valve:") and
                 (node["id"] in sig_to_mc or node["id"] in sig_to_btn or node["id"] in sig_to_sig))):
            deferred_mc.append(node)
            continue

        if role == "pressure_source":
            _place(node, memory_x + ps_offset_x, rows["infra"])
        elif role == "pressure_line_main":
            _place(node, 0.0, rows["infra"])
        elif role == "and_start":
            _place(node, cols["infra_and_offset_x"], rows["infra"])
        elif role.startswith("cylinder:"):
            letter = role.split(":", 1)[1]
            _place(node, cyl_col.get(letter, 0.0), rows["cylinder"])
        elif role.startswith("main_valve:"):
            letter = role.split(":", 1)[1]
            _place(node, cyl_col.get(letter, 0.0) + cols.get("v42_align_offset_x", -10),
                   rows["main_valve"])
        elif role.startswith("pressure_line_group:"):
            n = int(role.split(":", 1)[1])
            _place(node, pl_grp_x, rows["pl_grp_base"] + n * rows["pl_grp_gap"])
        elif role.startswith("signal_valve:"):
            # apenas sigs → v42 chegam aqui (as outras foram diferidas)
            nid = node["id"]
            v42_id, pilot_anc = sig_to_v42[nid]
            v42_pos = node_pos.get(v42_id)
            sig_A_x = _ANCHOR_LOCAL["Valve_3_2_Ways"]["A"][0]
            offset  = cols.get("sig_pilot_offset_PL" if pilot_anc == "PL"
                                else "sig_pilot_offset_PR", -50)
            if v42_pos:
                pl_x = _ANCHOR_LOCAL["Valve_4_2_Ways"][pilot_anc][0]
                x = v42_pos[0] + pl_x - sig_A_x + offset
            else:
                x = cyl_first_x
            _place(node, x, rows["main_valve"] + cols.get("sig_pilot_offset_y", 0))
        elif role.startswith("step_module:") or role.startswith("relay_coil:"):
            i = int(role.split(":", 1)[1])
            _place(node, i * step_mod_w, rows["steps"])
        elif role.startswith("relay_switch:"):
            i = int(role.split(":", 1)[1])
            _place(node, int((i + cols["relay_switch_half_offset"]) * step_mod_w), rows["steps"])
        elif role.startswith("solenoid_coil:"):
            _place(node, node.pop("_cyl_col_x", 0.0), rows["electric"])
        elif role == "voltage_source":
            _place(node, 0.0, rows["electric"])
        elif role == "ground":
            _place(node, cols.get("ground_dx", 100), rows["electric"])
        else:
            node.pop("_role", None)

    # ── Fase 2: filhos (Exhaust / PS) relativos ao pai ────────────────────────
    def _position_child(node: dict) -> bool:
        nid   = node["id"]
        ntype = node["type"]
        parent_id, parent_anc = child_parent[nid]
        if parent_id not in node_pos:
            return False
        px, py       = node_pos[parent_id]
        parent_local = _anchor_local(node_type_map.get(parent_id, ""), parent_anc)
        if parent_local is None:
            _place(node, px, py + 100)
        else:
            anc_x = px + parent_local[0]
            anc_y = py + parent_local[1]
            child_local = _anchor_local(ntype, _CHILD_CONNECT_ANCHOR[ntype])
            _place(node, anc_x - (child_local[0] if child_local else 0.0), anc_y + gap)
        return True

    deferred_late: list[dict] = []
    for node in deferred:
        if not _position_child(node):
            deferred_late.append(node)

    # ── Fase 2.5: memórias 5/2 ───────────────────────────────────────────────
    real_mc_nodes = sorted(
        [n for n in deferred_mc if n.get("_role","").startswith("memory:")],
        key=lambda n: int(n["_role"].split(":",1)[1])
    )
    btn_sig_nodes = [n for n in deferred_mc if not n.get("_role","").startswith("memory:")]

    n_mc_total = len(real_mc_nodes)
    pl_grp_gap = rows["pl_grp_gap"]
    pl_grp_base = rows["pl_grp_base"]
    pl_last_y  = pl_grp_base + n_mc_total * pl_grp_gap   # n_pl = n_mc + 1
    mc_top_y   = pl_last_y + round(1.370 * pl_grp_gap)
    gap_mc     = round(2.064 * pl_grp_gap)
    mc_top_x   = cyl_first_x + _M.cyl_width - _M.v52_width / 2 - 15

    mc_x_by_idx: dict[int, float] = {}
    mc_y_by_idx: dict[int, float] = {}

    for node in reversed(real_mc_nodes):
        n_idx = int(node["_role"].split(":",1)[1])
        steps = n_mc_total - 1 - n_idx
        x, y  = mc_top_x + steps * _M.mc_x_step, mc_top_y + steps * gap_mc
        mc_x_by_idx[n_idx] = x
        mc_y_by_idx[n_idx] = y
        _place(node, x, y)

    # filhos cujo pai era uma mc
    for node in deferred_late:
        _position_child(node)

    # ── Fase 2.6: btn e sigs dependentes das mc ───────────────────────────────
    cyl_last_x = cyl_first_x + (len(cyl_col) - 1) * cyl_group_w if cyl_col else cyl_first_x
    sig_below_btn_offset = cols.get("sig_below_btn_offset", 93)
    btn_height = 180
    btn_x = btn_y = 0.0

    btn_node = next((n for n in btn_sig_nodes if n.get("_role") == "button"), None)
    if btn_node:
        mc0_x = mc_x_by_idx.get(0, memory_x)
        mc0_y = mc_y_by_idx.get(0, mc_top_y)
        btn_x = mc0_x + btn_offset_x
        btn_y = mc0_y + round(0.974 * pl_grp_gap)
        _place(btn_node, btn_x, btn_y)

    sig_pr_off = (cols.get("sig_pilot_offset_PR", 59)
                  + cols.get("sig_pilot_offset_PR_per_mc", 0) * (n_mc_total - 1))
    V52_PR_x = _ANCHOR_LOCAL["Valve_5_2_Ways"]["PR"][0]
    SIG_A_x  = _ANCHOR_LOCAL["Valve_3_2_Ways"]["A"][0]

    for node in btn_sig_nodes:
        nid  = node["id"]
        role = node.get("_role", "")
        if role == "button":
            continue

        if nid in sig_to_mc:
            mc_id, _ = sig_to_mc[nid]
            mc_pos   = node_pos.get(mc_id)
            sig_x    = ((mc_pos[0] + V52_PR_x - SIG_A_x + sig_pr_off) if mc_pos
                        else cyl_last_x + cols.get("v42_align_offset_x", 65) + 256 - sig_pr_off - 254)
            if mc_pos:
                mc_idx = next((i for i, y in mc_y_by_idx.items()
                               if abs(y - mc_pos[1]) < 1), None)
                if mc_idx is not None and mc_idx > 0:
                    sig_y = (mc_y_by_idx[mc_idx] + mc_y_by_idx[mc_idx - 1]) / 2
                else:
                    sig_y = (btn_y + 23) if btn_y else mc_top_y + gap_mc + round(0.974 * pl_grp_gap) + 23
            else:
                sig_y = mc_top_y + gap_mc + round(0.974 * pl_grp_gap) + 23
            _place(node, sig_x, sig_y)

        elif nid in sig_to_btn:
            _place(node, btn_x, btn_y + btn_height + sig_below_btn_offset)

        elif nid in sig_to_sig:
            _place(node, cyl_last_x, mc_y_by_idx.get(0, rows["memory"]) + gap_mc / 2)

        else:
            node.pop("_role", None)

    # ── Fase 2.7: filhos cujo pai foi posicionado na fase 2.6 ────────────────
    for node in list(deferred_late):
        if node["id"] not in node_pos:
            _position_child(node)

    # ── Fase 2.8: centralizar PLs sobre seus componentes conectados ───────────
    pl_node_map = {n["id"]: n for n in data["nodes"] if n["type"] == "PressureLine"}

    pl_xs: dict[str, list[float]] = {pid: [] for pid in pl_node_map}
    for conn in data.get("connections", []):
        s_id, s_anc = conn["source"]["node"], conn["source"]["anchor"]
        t_id, t_anc = conn["target"]["node"], conn["target"]["anchor"]
        for pl_id, other_id, other_anc in [(s_id, t_id, t_anc), (t_id, s_id, s_anc)]:
            if pl_id not in pl_node_map:
                continue
            x = _scene_x(other_id, other_anc, node_pos, node_type_map)
            if x is not None:
                pl_xs[pl_id].append(x)

    all_xs = [x for xs in pl_xs.values() for x in xs]
    if all_xs:
        center = (min(all_xs) + max(all_xs)) / 2
        for pl_id, xs in pl_xs.items():
            if not xs:
                continue
            pl_node  = pl_node_map[pl_id]
            n_anch   = len(pl_node["properties"]["anchors"])
            pl_width = _M.pl_pix_w / 2 + (n_anch - 1) * _M.pl_spacing
            new_x    = center - pl_width / 2
            pl_node["position"]["x"] = new_x
            node_pos[pl_id] = (new_x, node_pos[pl_id][1])

    # ── Fase 3: atribuir anchors das PressureLines ────────────────────────────
    pl_anchor_used: dict[int, tuple[str, float]] = {}  # round(x) → (owner_id, owner_y)
    conn_by_owner:  dict[str, tuple]             = {}  # owner_id → (conn, side, pl_node)
    mc_A_anchor:    dict[str, tuple[str, int]]   = {}  # mc_id → (pl_id, idx)

    def _resolve_conflict(pl_node: dict, anchor: str, owner: str,
                           owner_y: float, conn_ref: object, side: str) -> str:
        anchors = pl_node["properties"]["anchors"]
        n, mid  = len(anchors), len(anchors) / 2

        def _next(anc: str) -> str:
            idx = int(anc[1:])
            return f"X{max(1, min(n, (idx-1) if idx <= mid else (idx+1)))}"

        def _reg(anc: str, oid: str, oy: float, cref: object) -> str:
            ax  = _pl_anchor_x(pl_node, anc, node_pos)
            key = round(ax)
            if key not in pl_anchor_used:
                pl_anchor_used[key] = (oid, oy)
                conn_by_owner[oid]  = (cref, side, pl_node)
                return anc
            prev_id, prev_y = pl_anchor_used[key]
            if prev_id == oid:
                return anc
            if oy >= prev_y:
                return _reg(_next(anc), oid, oy, cref)
            else:
                pl_anchor_used[key] = (oid, oy)
                conn_by_owner[oid]  = (cref, side, pl_node)
                prev_conn, prev_side, prev_pl = conn_by_owner.get(prev_id, (None, None, None))
                if prev_conn is not None:
                    new_anc = _reg(_next(anc), prev_id, prev_y, prev_conn)
                    prev_conn[prev_side]["anchor"] = new_anc
                return anc

        return _reg(anchor, owner, owner_y, conn_ref)

    # Processar caso 2 (componente → PL) antes do caso 1 (PL → componente)
    # para registrar no pl_anchor_used antes de resolver conflitos
    connections_sorted = sorted(
        [c for c in data.get("connections", [])
         if c["source"]["node"] != c["target"]["node"]],
        key=lambda c: 0 if c["target"]["node"] in pl_node_map else 1
    )

    for conn in connections_sorted:
        s_id, s_anc = conn["source"]["node"], conn["source"]["anchor"]
        t_id, t_anc = conn["target"]["node"], conn["target"]["anchor"]
        s_type = node_type_map.get(s_id, "")
        t_type = node_type_map.get(t_id, "")

        if s_id in pl_node_map and s_anc.startswith("X"):
            # PL → componente
            tgt_x = _scene_x(t_id, t_anc, node_pos, node_type_map)
            if tgt_x is None:
                continue
            pl = pl_node_map[s_id]
            pl_y  = node_pos.get(s_id, (0,0))[1]
            tgt_y = (node_pos.get(t_id, (0,0))[1] + 180) if t_type == "Valve_3_2_Ways" else 0
            if t_type == "Valve_3_2_Ways" and t_anc == "P":
                y0, y1 = (pl_y, tgt_y) if tgt_y > pl_y else (tgt_y, pl_y)
                if y0 != y1:
                    anc = _best_pl_anchor_clear_column(pl, tgt_x, y0, y1,
                                                        node_pos, node_type_map, pl_anchor_used)
                else:
                    anc = _nearest_pl_anchor(pl, tgt_x, node_pos)
            elif t_anc == "PL":
                anc = _nearest_pl_anchor(pl, tgt_x, node_pos, "left")
            elif t_anc == "PR":
                anc = _nearest_pl_anchor(pl, tgt_x, node_pos, "right")
            else:
                anc = _nearest_pl_anchor(pl, tgt_x, node_pos)
            conn["source"]["anchor"] = _resolve_conflict(
                pl, anc, t_id, node_pos.get(t_id,(0,0))[1], conn, "source")

        elif t_id in pl_node_map and t_anc.startswith("X"):
            # componente → PL
            src_x = _scene_x(s_id, s_anc, node_pos, node_type_map)
            if src_x is None:
                continue
            pl = pl_node_map[t_id]
            OFF = 10
            if s_anc == "PL":
                anc = _nearest_pl_anchor(pl, src_x - OFF, node_pos, "left")
            elif s_anc == "PR":
                anc = _nearest_pl_anchor(pl, src_x + OFF, node_pos, "right")
            elif s_type == "Valve_5_2_Ways" and s_anc == "A":
                ax  = node_pos.get(s_id,(0,0))[0] + _ANCHOR_LOCAL["Valve_5_2_Ways"]["A"][0]
                anc = _nearest_pl_anchor(pl, ax, node_pos)
            elif s_type == "Valve_5_2_Ways" and s_anc == "B":
                bx  = node_pos.get(s_id,(0,0))[0] + _ANCHOR_LOCAL["Valve_5_2_Ways"]["B"][0]
                anc = _nearest_pl_anchor(pl, bx + cols.get("mc_B_pl_margin", 30), node_pos, "right")
            else:
                anc = _nearest_pl_anchor(pl, src_x, node_pos)
            conn["target"]["anchor"] = _resolve_conflict(
                pl, anc, s_id, node_pos.get(s_id,(0,0))[1], conn, "target")
            if s_type == "Valve_5_2_Ways" and s_anc == "A":
                mc_A_anchor[s_id] = (t_id, int(conn["target"]["anchor"][1:]))

    # ── Fase 3.5: mc.B anchor > mc.A anchor (evita cruzamento) ───────────────
    for conn in data.get("connections", []):
        s_id, s_anc = conn["source"]["node"], conn["source"]["anchor"]
        t_id = conn["target"]["node"]
        if (node_type_map.get(s_id) == "Valve_5_2_Ways" and s_anc == "B"
                and t_id in pl_node_map):
            _, a_idx = mc_A_anchor.get(s_id, (None, -1))
            if a_idx != -1:
                b_idx     = int(conn["target"]["anchor"][1:])
                n_anchors = len(pl_node_map[t_id]["properties"]["anchors"])
                if b_idx <= a_idx:
                    conn["target"]["anchor"] = f"X{min(a_idx + 1, n_anchors)}"

    # ── Fase 3.9: pruning das PressureLines ──────────────────────────────────
    used_min, used_max = float("inf"), float("-inf")
    for conn in data.get("connections", []):
        for side in (conn["source"], conn["target"]):
            if side["node"] in pl_node_map and side["anchor"].startswith("X"):
                idx = int(side["anchor"][1:])
                used_min = min(used_min, idx)
                used_max = max(used_max, idx)

    if used_min != float("inf"):
        for pl_id, pl_node in pl_node_map.items():
            all_idxs = [int(a[1:]) for a in pl_node["properties"]["anchors"]]
            keep_min = max(min(all_idxs), used_min - 1)
            keep_max = min(max(all_idxs), used_max + 1)
            pl_node["properties"]["anchors"] = [f"X{i}" for i in all_idxs
                                                if keep_min <= i <= keep_max]
            old_x = node_pos[pl_id][0]
            new_x = old_x + (keep_min - 1) * _M.pl_spacing
            pl_node["position"]["x"] = new_x
            node_pos[pl_id] = (new_x, node_pos[pl_id][1])

    # ── Fase 4: roteamento A* ─────────────────────────────────────────────────
    from circuit_generator.astar_router import build_grid, route_connection, get_exit_dir
    astar_grid = build_grid(data["nodes"])

    for conn in data.get("connections", []):
        s_id, s_anc = conn["source"]["node"], conn["source"]["anchor"]
        t_id, t_anc = conn["target"]["node"], conn["target"]["anchor"]
        spos = _scene_xy(s_id, s_anc, node_pos, node_type_map)
        tpos = _scene_xy(t_id, t_anc, node_pos, node_type_map)
        if spos is None or tpos is None:
            continue
        s_type = node_type_map.get(s_id, "")
        t_type = node_type_map.get(t_id, "")
        wps = route_connection(astar_grid, spos, get_exit_dir(s_type, s_anc),
                                tpos, get_exit_dir(t_type, t_anc),
                                src_type=s_type, tgt_type=t_type,
                                src_id=s_id, tgt_id=t_id)
        if wps is not None:
            conn["waypoints"] = wps

    return data