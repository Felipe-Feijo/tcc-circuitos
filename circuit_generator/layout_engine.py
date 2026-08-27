"""Motor de posicionamento espacial dos componentes gerados.

Recebe o dicionário de dados do circuito (com _role em cada nó) e preenche
as posições x/y de cada componente com base nas regras de layout definidas
em layout_config.json e nas métricas de sprites em sprite_metrics.py.
"""

import json
from circuit_generator.sprite_metrics import METRICS as _M, anchor_local_for_routing
from paths import get_base_dir

_CONFIG_PATH = get_base_dir() / "circuit_generator" / "layout_config.json"

_ANCHOR_LOCAL: dict[str, dict[str, tuple[float, float]]] = _M.anchor_local

# Tipos-filho que se posicionam relativos ao pai (Exhaust/PS)
_CHILD_CONNECT_ANCHOR: dict[str, str] = {
    "Exhaust":        "R",
    "PressureSource": "P",
}


def _anchor_local(node_type: str, anchor_name: str) -> tuple[float, float] | None:
    return anchor_local_for_routing(node_type, anchor_name)


def _scene_x(node_id: str, anchor_name: str,
              node_pos: dict, node_type_map: dict) -> float | None:
    """Posição X em cena de um anchor de qualquer nó posicionado."""
    npos  = node_pos.get(node_id)
    ntype = node_type_map.get(node_id, "")
    if npos is None:
        return None
    local = _anchor_local(ntype, anchor_name)
    return (npos[0] + local[0]) if local else npos[0]


def _scene_xy(node_id: str, anchor_name: str,
               node_pos: dict, node_type_map: dict) -> tuple[float, float] | None:
    """Posição (X, Y) em cena de um anchor de qualquer nó posicionado."""
    npos  = node_pos.get(node_id)
    ntype = node_type_map.get(node_id, "")
    if npos is None:
        return None
    local = _anchor_local(ntype, anchor_name)
    return (npos[0] + local[0], npos[1] + local[1]) if local else npos


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
    pl_grp_x     = cols["pl_grp_x"]
    memory_x     = cols["memory_x"]
    btn_offset_x = cols["btn_offset_x"]
    ps_offset_x  = cols["ps_offset_x"]
    step_mod_w   = cols["step_module_width"]

    # ── Mapas auxiliares ─────────────────────────────────────────────────────
    node_type_map: dict[str, str] = {n["id"]: n["type"] for n in data["nodes"]}
    role_map:      dict[str, str] = {n["id"]: n.get("_role", "") for n in data["nodes"]}

    # letter → coluna x da 4/2 (calculado por cursor após dry-run)
    cyl_col: dict[str, float] = {}

    node_pos: dict[str, tuple[float, float]] = {}

    # ── Varredura de conexões: montar todos os mapas de uma vez ──────────────
    child_parent:    dict[str, tuple[str, str]] = {}
    sig_to_v42:      dict[str, tuple[str, str]] = {}
    sig_to_or:       dict[str, tuple[str, str]] = {}
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

        # sig → OrValve (multi-ciclo: sig alimenta uma convergência OR em
        # vez do pilot da 4/2 diretamente)
        if (s_type == "Valve_3_2_Ways" and s_anc == "A" and
                t_type == "OrValve" and t_anc in ("X", "Y") and
                s_role.startswith("signal_valve:")):
            sig_to_or[s_id] = (t_id, t_anc)

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


    # ── Footprint dos grupos: cursor calcula x_v42 de cada letra ────────────
    v42_to_sigs: dict[str, list[tuple[str, str]]] = {}
    for sig_id, (v42_id, pilot_anc) in sig_to_v42.items():
        v42_to_sigs.setdefault(v42_id, []).append((sig_id, pilot_anc))

    v42_by_letter: dict[str, str] = {}
    for nid, role in role_map.items():
        if role.startswith("main_valve:"):
            letter = role.split(":", 1)[1]
            v42_by_letter[letter] = nid

    _v42_aln      = cols.get("v42_align_offset_x", 65)
    _V42_PL_x     = _ANCHOR_LOCAL["Valve_4_2_Ways"]["PL"][0]
    _V42_PR_x     = anchor_local_for_routing("Valve_4_2_Ways", "PR")[0]
    _SIG_A_x      = _ANCHOR_LOCAL["Valve_3_2_Ways"]["A"][0]
    _group_gap    = cols.get("group_gap", 300)
    _sig_base_off = cols.get("sig_base_offset", 400)  # offset do anchor A da 1a col a borda do sprite da 4/2
    _sig_spacing  = _M.sig_spacing                    # distancia entre colunas adjacentes

    # PL fica em x negativo (fora do sprite a esquerda): borda esquerda = x=0, PL_x < 0
    # PR fica alem da largura (fora a direita): borda direita = v42_width, PR_x > v42_width
    # Compensamos para que sig_base_offset seja sempre medido a partir da borda do sprite,
    # garantindo simetria visual independente da posicao dos anchors PL/PR.
    _PL_border_excess = abs(min(_V42_PL_x, 0))           # quanto PL ultrapassa a borda esq
    _PR_border_excess = max(_V42_PR_x - _M.v42_width, 0) # quanto PR ultrapassa a borda dir

    # Pre-computa posicoes X das colunas de sigs de cada grupo relativas a x_v42=0.
    # Retorna lista de dx do anchor A para cada coluna, de dentro pra fora.
    def _sig_col_xs(v42_id: str, pilot_anc: str) -> list[float]:
        sigs = [s for s, anc in v42_to_sigs.get(v42_id, []) if anc == pilot_anc]
        pilot_x = _V42_PL_x if pilot_anc == "PL" else _V42_PR_x
        sign    = -1 if pilot_anc == "PL" else 1
        excess  = _PL_border_excess if pilot_anc == "PL" else _PR_border_excess
        return [pilot_x - _SIG_A_x + sign * (_sig_base_off + excess + i * _sig_spacing)
                for i in range(len(sigs))]

    # Mapa: (v42_id, pilot_anc) -> lista ordenada de dx dos anchors A das colunas
    sig_col_x_map: dict[tuple[str,str], list[float]] = {}

    x_cursor = cyl_first_x
    for letter in sorted(v42_by_letter):
        v42_id = v42_by_letter[letter]

        # Footprint base: 4/2 e cilindro
        offsets: list[tuple[float, float]] = [
            (0.0,        float(_M.v42_width)),
            (-_v42_aln,  -_v42_aln + _M.cyl_width),
        ]

        # Footprint das colunas de sigs por pilot
        for pilot_anc in ("PL", "PR"):
            col_xs = _sig_col_xs(v42_id, pilot_anc)
            sig_col_x_map[(v42_id, pilot_anc)] = col_xs
            for ax_dx in col_xs:
                # footprint da coluna = fp_left a esquerda do A, fp_right a direita
                offsets.append((ax_dx - _M.sig_fp_left, ax_dx + _M.sig_fp_right))

        x_min = min(x0 for x0, _ in offsets)
        x_max = max(x1 for _, x1 in offsets)

        # x_v42 tal que x_min do grupo caia em x_cursor
        x_v42 = x_cursor - x_min
        cyl_col[letter] = x_v42

        x_cursor = x_v42 + x_max + _group_gap


    # ── Fase 1: nós primários ─────────────────────────────────────────────────
    deferred:    list[dict] = []  # Exhaust / PS
    deferred_mc: list[dict] = []  # memórias, btn, sigs que dependem das mc

    def _place(node: dict, x: float, y: float) -> None:
        node["position"] = {"x": x, "y": y}
        node_pos[node["id"]] = (x, y)
        node.pop("_role", None)

    def _or_valve_xy(letter: str, pilot_side: str, chain_i: int) -> float:
        base_x    = cyl_col.get(letter, cyl_first_x)
        side_sign = -1 if pilot_side == "PL" else 1
        return base_x + side_sign * (cols.get("or_valve_base_offset_x", 600)
                                      + chain_i * cols.get("or_valve_chain_step_x", 250))

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
        elif role.startswith("signal_valve:") and node["id"] in sig_to_v42:
            # sig → v42 direto (a maioria) chega aqui
            nid = node["id"]
            v42_id, pilot_anc = sig_to_v42[nid]
            v42_pos = node_pos.get(v42_id)
            if v42_pos:
                col_xs  = sig_col_x_map.get((v42_id, pilot_anc), [])
                # determina qual coluna esta sig ocupa (ordem de chegada)
                placed  = sum(1 for n2 in data["nodes"]
                              if n2.get("_role","").startswith("signal_valve:")
                              and n2["id"] != nid
                              and n2["id"] in sig_to_v42
                              and sig_to_v42[n2["id"]] == (v42_id, pilot_anc)
                              and n2.get("position") is not None)
                dx = col_xs[placed] if placed < len(col_xs) else col_xs[-1]
                x  = v42_pos[0] + dx
            else:
                x = cyl_first_x
            _place(node, x, rows["main_valve"] + cols.get("sig_pilot_offset_y", 0))
        elif role.startswith("signal_valve:") and node["id"] in sig_to_or:
            # sig → OrValve (multi-ciclo): sem coluna própria — posição
            # baseada na posição da própria OrValve alvo (mesma fórmula do
            # branch or_valve: acima, via _or_valve_xy), deslocada conforme
            # o anchor (X ou Y) que este sig alimenta, para que os dois
            # sigs que alimentam a mesma OrValve nunca coincidam. Rústico
            # até o motor de grid genérico existir (sub-projeto futuro).
            nid              = node["id"]
            or_id, or_anchor = sig_to_or[nid]
            or_role          = role_map.get(or_id, "")
            if or_role.startswith("or_valve:"):
                _, letter, pilot_side, chain_i = or_role.split(":")
                or_x = _or_valve_xy(letter, pilot_side, int(chain_i))
            else:
                or_x = cyl_first_x
            anchor_spread = cols.get("or_orphan_sig_anchor_spread", 300)
            x = or_x - anchor_spread if or_anchor == "X" else or_x + anchor_spread
            _place(node, x, rows["main_valve"] + cols.get("sig_pilot_offset_y", 0))
        elif role.startswith("or_valve:"):
            # multi-ciclo: posição simples baseada em cyl_col, sem integrar
            # no sistema de colunas — rústico até o motor de grid genérico
            # existir (sub-projeto futuro).
            _, letter, pilot_side, chain_i = role.split(":")
            x = _or_valve_xy(letter, pilot_side, int(chain_i))
            _place(node, x, rows["main_valve"] + cols.get("or_valve_offset_y", -200))
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
    cyl_last_x = max(cyl_col.values()) if cyl_col else cyl_first_x
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

    sig_pr_off = (cols.get("sig_mc_pilot_offset_PR", 500)
                  + cols.get("sig_pilot_offset_PR_per_mc", 0) * (n_mc_total - 1))
    V52_PR_x = anchor_local_for_routing("Valve_5_2_Ways", "PR")[0]
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
            pl_node   = pl_node_map[pl_id]
            anchors   = pl_node["properties"]["anchors"]
            first_idx = int(anchors[0][1:])
            last_idx  = int(anchors[-1][1:])
            # X1 estaria em node_x + pl_pix_w/2, então X_first está em node_x + pl_pix_w/2 + (first_idx-1)*spacing
            # Centralizar significa que o centro da faixa usada fica em `center`
            mid_idx   = (first_idx + last_idx) / 2
            new_x     = center - (_M.pl_pix_w / 2 + (mid_idx - 1) * _M.pl_spacing)
            pl_node["position"]["x"] = new_x
            node_pos[pl_id] = (new_x, node_pos[pl_id][1])

    # ── Fase 3: atribuir taps das PressureLines (RailPlanner) ─────────────────
    from circuit_generator.rail import RailPlanner

    rail = RailPlanner(min_spacing=_M.pl_spacing)
    for pl_id, pl_node in pl_node_map.items():
        idxs = [int(a[1:]) for a in pl_node["properties"]["anchors"]]
        pl_x = node_pos[pl_id][0]
        x_min = pl_x + _M.pl_pix_w / 2 + (min(idxs) - min(idxs)) * _M.pl_spacing
        x_max = pl_x + _M.pl_pix_w / 2 + (max(idxs) - min(idxs)) * _M.pl_spacing
        rail.register_bus(pl_id, "PressureLineTerminal", y=node_pos[pl_id][1],
                           x_min=x_min, x_max=x_max)

    # Processar caso 2 (componente → PL) antes do caso 1 (PL → componente)
    # para registrar no pl_anchor_used antes de resolver conflitos
    def _conn_sort_key(c):
        s_id, s_anc = c["source"]["node"], c["source"]["anchor"]
        t_id = c["target"]["node"]
        is_to_pl = t_id in pl_node_map
        if not is_to_pl:
            return (2, 0)  # PL → componente: por último
        if node_type_map.get(s_id) == "Valve_5_2_Ways" and s_anc == "PL":
            return (0, 0)  # mc.PL → PL: primeiro (lado esquerdo)
        if node_type_map.get(s_id) == "Valve_5_2_Ways" and s_anc == "B":
            return (1, -node_pos.get(s_id, (0, 0))[1])  # mc.B → PL: depois, mc[0] (maior y) por último
        return (1, 0)  # resto: junto com mc.B

    connections_sorted = sorted(
        [c for c in data.get("connections", [])
         if c["source"]["node"] != c["target"]["node"]],
        key=_conn_sort_key
    )

    for conn in connections_sorted:
        s_id, s_anc = conn["source"]["node"], conn["source"]["anchor"]
        t_id, t_anc = conn["target"]["node"], conn["target"]["anchor"]
        s_type = node_type_map.get(s_id, "")

        if s_id in pl_node_map and s_anc.startswith("X"):
            # PL → componente: pede tap direto na posição real do alvo.
            # request_tap resolve colisão/ordenação sozinho (substitui os
            # antigos casos especiais por side/_best_pl_anchor_clear_column
            # -- ver task-4-report.md sobre a regressão conhecida e não
            # portada de _best_pl_anchor_clear_column).
            tgt_x = _scene_x(t_id, t_anc, node_pos, node_type_map)
            if tgt_x is None:
                continue
            rail.request_tap(s_id, owner_id=t_id, owner_y=node_pos.get(t_id, (0, 0))[1],
                              desired_x=tgt_x, conn_ref=conn, side="source")

        elif t_id in pl_node_map and t_anc.startswith("X"):
            # componente → PL
            src_x = _scene_x(s_id, s_anc, node_pos, node_type_map)
            if src_x is None:
                continue
            OFF_PL = cols.get("v42_pl_exit_offset", 10)
            OFF_PR = cols.get("v42_pr_exit_offset", 150)
            if s_anc == "PL" and s_type == "Valve_5_2_Ways":
                mc_role   = role_map.get(s_id, "")
                mc_idx    = int(mc_role.split(":", 1)[1]) if mc_role.startswith("memory:") else 0
                desired_x = src_x - mc_idx * 2 * _M.pl_spacing
            elif s_anc == "PL":
                desired_x = src_x - OFF_PL
            elif s_anc == "PR":
                desired_x = src_x + OFF_PR
            elif s_type == "Valve_5_2_Ways" and s_anc == "A":
                desired_x = node_pos.get(s_id,(0,0))[0] + _ANCHOR_LOCAL["Valve_5_2_Ways"]["A"][0]
            elif s_type == "Valve_5_2_Ways" and s_anc == "B":
                bx        = node_pos.get(s_id,(0,0))[0] + _ANCHOR_LOCAL["Valve_5_2_Ways"]["B"][0]
                safeguard = cols.get("mc_B_pl_safeguard", 20)
                PR_B_diff = anchor_local_for_routing("Valve_5_2_Ways", "PR")[0] - _ANCHOR_LOCAL["Valve_5_2_Ways"]["B"][0]
                margin    = PR_B_diff + 2.5 * _M.mc_x_step + safeguard
                desired_x = bx + margin
            else:
                desired_x = src_x
            rail.request_tap(t_id, owner_id=s_id, owner_y=node_pos.get(s_id, (0, 0))[1],
                              desired_x=desired_x, conn_ref=conn, side="target")

    # ── Fase 4: roteamento A* ─────────────────────────────────────────────────
    rail.materialize(data, {n["id"]: n for n in data["nodes"]}, node_pos)
    node_type_map = {n["id"]: n["type"] for n in data["nodes"]}

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