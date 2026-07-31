"""
Posicionamento espacial do método passo a passo elétrico.

Recebe o dicionário de dados do circuito (com _role em cada nó, gerado por
circuit_generator.methods.step_by_step_electric) e preenche as posições x/y
de cada componente usando circuit_generator.grid_layout.Grid.

v0 -- ver docs/superpowers/specs/2026-07-30-step-by-step-electric-layout-design.md.
Reaproveita o ALGORITMO (não o código) da região de pistões/válvulas de
step_by_step_layout.py (pneumático) -- mesmo _role scheme
(cylinder:{letra}, main_valve:{letra}, or_valve:{letra}:{lado}:{i}).

Faixas verticais (topo -> base):
  1. Pistões/válvulas + cadeia sig/OrValve de multi-ciclo (mesmo _role
     scheme do pneumático para cilindro/válvula/OrValve; a cadeia de sigs
     em si -- Valve_3_2_Ways com role pilot_sig:{letra}:{direção}:{k} --
     não tem análogo pneumático nesta região, porque lá a OrValve é
     alimentada direto pela PressureLine -- aqui cada sig precisa de
     posição própria, ver _place_pilot_sig_chain()).
  2. VoltageSource (barra horizontal).
  3. Zona 1 (esquerda): bloco por átomo -- ramo A | ramo B | botão (só no
     último átomo) -- e Zona 2 (à DIREITA de toda a Zona 1, mesma faixa Y):
     reset (NC) empilhado sobre a bobina Y_k, um bloco denso por átomo.
  4. Ground (barra horizontal).

Fora de escopo (v0, confirmado com o usuário): reatribuição de anchor da
VoltageSource/Ground por proximidade real de tela -- os anchors renderizam
na ordem sequencial que a topologia já atribuiu (next_bus_anchor()).
"""

from circuit_generator.grid_layout import Grid
from circuit_generator.sprite_metrics import METRICS as _M, anchor_local_for_routing


def _build_role_maps(data: dict) -> dict:
    role_map = {n["id"]: n.get("_role", "") for n in data["nodes"]}

    cyl_by_letter: dict[str, str] = {}
    v42_by_letter: dict[str, str] = {}
    coil_by_idx: dict[int, str] = {}
    contact_by_role: dict[str, str] = {}
    vsource_id: str | None = None
    ground_id: str | None = None
    btn_id: str | None = None

    for nid, role in role_map.items():
        if role.startswith("cylinder:"):
            cyl_by_letter[role.split(":", 1)[1]] = nid
        elif role.startswith("main_valve:"):
            v42_by_letter[role.split(":", 1)[1]] = nid
        elif role.startswith("coil:"):
            coil_by_idx[int(role.split(":", 1)[1])] = nid
        elif role.startswith("contact:"):
            contact_by_role[role.split(":", 1)[1]] = nid
        elif role == "voltage_source":
            vsource_id = nid
        elif role == "ground":
            ground_id = nid
        elif role == "button":
            btn_id = nid

    return {
        "role_map":       role_map,
        "cyl_by_letter":  cyl_by_letter,
        "v42_by_letter":  v42_by_letter,
        "coil_by_idx":    coil_by_idx,
        "contact_by_role": contact_by_role,
        "vsource_id":     vsource_id,
        "ground_id":      ground_id,
        "btn_id":         btn_id,
        "n_atoms":        len(coil_by_idx),
    }


def _place_pilot_sig_chain(data: dict, grid: Grid, node_by_id: dict,
                            or_nodes: list, or_virtual_col: dict,
                            or_row_y: float, cyl_cell_w: float,
                            cyl_first_x: float, _place_aligned) -> None:
    """Posiciona os nós Valve_3_2_Ways (role pilot_sig:{letra}:{direção}:{k})
    que alimentam a cadeia de OrValve de multi-ciclo.

    Sem análogo no algoritmo pneumático: lá a OrValve é alimentada direto
    pela PressureLine (nenhum nó extra precisa de posição); aqui cada
    ocorrência do evento tem seu próprio sig dedicado (lê o sensor Y_k),
    então a cadeia tem 1 sig a mais que OrValves.

    Réplica da ordem determinística de step_by_step_electric.generate():
    para cada (letra, lado), os sigs são criados em ordem crescente de
    k (índice do átomo) -- essa é exatamente a ordem "sig_outputs" usada
    lá para montar a cadeia de OrValve (sig[0] e sig[1] alimentam a
    primeira OrValve da cadeia; sig[i], i>=2, alimenta a OrValve[i-1]).
    Reaproveita as MESMAS colunas virtuais já atribuídas às OrValve
    (nenhum orçamento extra de coluna é necessário) -- sig[0]/sig[1]
    empilham na coluna da primeira OrValve (profundidades 1/2); os
    demais ficam 1 nível acima da OrValve que alimentam.
    """
    pilot_sig_nodes = [n for n in data["nodes"] if n["_role"].startswith("pilot_sig:")]
    if not pilot_sig_nodes:
        return

    or_vcol_by_key: dict[tuple[str, str, int], int] = {}
    for n in or_nodes:
        _, or_letter, or_side, or_i = n["_role"].split(":")
        or_vcol_by_key[(or_letter, or_side, int(or_i))] = or_virtual_col[n["id"]]

    sig_by_group: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for n in pilot_sig_nodes:
        _, letter, direction, k = n["_role"].split(":")
        side = "PL" if direction == "+" else "PR"
        sig_by_group.setdefault((letter, side), []).append((int(k), n["id"]))

    sig_vcol: dict[str, int] = {}
    sig_depth: dict[str, int] = {}
    for (letter, side), items in sig_by_group.items():
        items.sort()
        for i, (_k, sig_id) in enumerate(items):
            or_i = 0 if i <= 1 else i - 1
            sig_vcol[sig_id] = or_vcol_by_key[(letter, side, or_i)]
            sig_depth[sig_id] = 2 if i == 1 else 1

    min_vcol = min(sig_vcol.values())
    for depth in (1, 2):
        row_id = f"pilot_sig_row_{depth}"
        # Deslocamento (250, não 200) escolhido pra nunca coincidir
        # exatamente com or_row_y (200) -- evita um nó cair em y=0 quando
        # x também dá 0 (grupo mais à esquerda, min_vcol da própria coluna).
        grid.add_row(row_id, cyl_cell_w, _M.v32_height, or_row_y - depth * 250.0,
                     x_origin=cyl_first_x + min_vcol * cyl_cell_w)

    for sig_id, vcol in sorted(sig_vcol.items(), key=lambda kv: kv[1]):
        row_id = f"pilot_sig_row_{sig_depth[sig_id]}"
        x, y = _place_aligned(row_id, vcol - min_vcol, sig_id)
        node_by_id[sig_id]["position"] = {"x": x, "y": y}


def apply(data: dict) -> dict:
    node_type_map = {n["id"]: n["type"] for n in data["nodes"]}
    node_by_id = {n["id"]: n for n in data["nodes"]}
    roles = _build_role_maps(data)
    n_atoms = roles["n_atoms"]

    grid = Grid()
    _reserved_cols: dict[str, set[int]] = {}

    def _place_aligned(row_id: str, virtual_col: int, node_id: str) -> tuple[float, float]:
        reserved = _reserved_cols.setdefault(row_id, set())
        for kk in range(virtual_col):
            if kk not in reserved:
                grid.place(row_id, kk, f"__reserved__{row_id}__{kk}__")
                reserved.add(kk)
        reserved.add(virtual_col)
        return grid.place(row_id, virtual_col, node_id)

    # ── Config (v0: hardcoded, sem arquivo json externo -- só uma etapa,
    #    diferente do pneumático que já tinha um config compartilhado por
    #    várias etapas históricas) ──────────────────────────────────────
    cyl_cell_w = 300
    cyl_first_x = 0.0
    cyl_row_y = 0.0
    v42_row_y = 400.0
    or_row_y = 200.0
    vsource_row_y = 700.0
    ramo_row_y = 900.0
    ramo_stack_gap = 150.0
    zone_gap = 400.0
    reset_row_y = ramo_row_y
    coil_row_y = ramo_row_y + 150.0
    ground_row_y = coil_row_y + 300.0
    ramo_cell_w = 200.0
    zone2_cell_w = 200.0

    # ── Região de pistões/válvulas + cadeia OrValve (multi-ciclo) --
    #    algoritmo idêntico ao pneumático, mesmo _role scheme ─────────────
    or_nodes = [n for n in data["nodes"] if n["type"] == "OrValve"]
    or_chain_len: dict[tuple[str, str], int] = {}
    for n in or_nodes:
        _, or_letter, or_side, _or_i = n["_role"].split(":")
        key = (or_letter, or_side)
        or_chain_len[key] = or_chain_len.get(key, 0) + 1

    def _pilot_reserve(letter: str, side: str) -> int:
        return max(1, or_chain_len.get((letter, side), 0))

    letters = sorted(roles["cyl_by_letter"])
    cyl_col: dict[str, int] = {}
    col = 0
    for letter in letters:
        col += _pilot_reserve(letter, "PL")
        cyl_col[letter] = col
        col += 1 + _pilot_reserve(letter, "PR")

    grid.add_row("cylinder", cyl_cell_w, _M.cyl_height, cyl_row_y, x_origin=cyl_first_x)
    grid.add_row("main_valve", cyl_cell_w, _M.v42_height, v42_row_y, x_origin=cyl_first_x)

    for letter in letters:
        cyl_id = roles["cyl_by_letter"][letter]
        v42_id = roles["v42_by_letter"][letter]
        x, y = _place_aligned("cylinder", cyl_col[letter], cyl_id)
        node_by_id[cyl_id]["position"] = {"x": x, "y": y}
        x, y = _place_aligned("main_valve", cyl_col[letter], v42_id)
        node_by_id[v42_id]["position"] = {"x": x, "y": y}

    or_virtual_col: dict[str, int] = {}
    if or_nodes:
        for n in or_nodes:
            _, or_letter, or_side, or_i = n["_role"].split(":")
            sign = -1 if or_side == "PL" else 1
            offset = or_chain_len[(or_letter, or_side)] - int(or_i)
            or_virtual_col[n["id"]] = cyl_col[or_letter] + sign * offset

        min_vcol = min(or_virtual_col.values())
        grid.add_row("or_row", cyl_cell_w, _M.or_height, or_row_y,
                     x_origin=cyl_first_x + min_vcol * cyl_cell_w)
        for n in sorted(or_nodes, key=lambda n: or_virtual_col[n["id"]]):
            vcol = or_virtual_col[n["id"]]
            x, y = _place_aligned("or_row", vcol - min_vcol, n["id"])
            node_by_id[n["id"]]["position"] = {"x": x, "y": y}

        _place_pilot_sig_chain(data, grid, node_by_id, or_nodes, or_virtual_col,
                                or_row_y, cyl_cell_w, cyl_first_x, _place_aligned)

    # ── VoltageSource (barra horizontal, topo da faixa elétrica) ─────────
    vsource_id = roles["vsource_id"]
    node_by_id[vsource_id]["position"] = {"x": cyl_first_x, "y": vsource_row_y}

    # ── Zona 1: bloco por átomo (ramo A | ramo B | botão) ────────────────
    grid.add_row("ramo_row", ramo_cell_w, _M.relay_switch_height, ramo_row_y,
                 x_origin=cyl_first_x)

    contact_by_role = roles["contact_by_role"]

    def _contact(role_key: str) -> str:
        return contact_by_role[role_key]

    stack_rows_added: set[str] = set()
    for k in range(n_atoms):
        # Ramo A: cadeia de contatos de sensor (i=0,1,...) + contato do Y anterior.
        # A ordem da cadeia é a ORDEM DE CRIAÇÃO em step_by_step_electric.py
        # (0-indexada, i crescente) -- empilha pra CIMA (y decrescente),
        # ficando o contato do Y anterior sempre na linha-base (ramo_row).
        sensor_roles = sorted(
            k2 for k2 in contact_by_role if k2.startswith(f"{k}-ramo_a_sensor")
        )
        prev_role = f"{k}-ramo_a_prev"
        prev_id = _contact(prev_role)
        x, y = _place_aligned("ramo_row", 3 * k, prev_id)
        node_by_id[prev_id]["position"] = {"x": x, "y": y}
        for depth, sensor_role in enumerate(reversed(sensor_roles), start=1):
            sensor_id = _contact(sensor_role)
            stack_row_id = f"ramo_a_stack_{depth}"
            if stack_row_id not in stack_rows_added:
                grid.add_row(stack_row_id, ramo_cell_w, _M.relay_switch_height,
                             ramo_row_y - depth * ramo_stack_gap, x_origin=cyl_first_x)
                stack_rows_added.add(stack_row_id)
            x, y = _place_aligned(stack_row_id, 3 * k, sensor_id)
            node_by_id[sensor_id]["position"] = {"x": x, "y": y}

        # Ramo B: self-hold do próprio Y_k.
        self_id = _contact(f"{k}-ramo_b_self")
        x, y = _place_aligned("ramo_row", 3 * k + 1, self_id)
        node_by_id[self_id]["position"] = {"x": x, "y": y}

        # Botão de bootstrap: só o último átomo.
        if k == n_atoms - 1:
            btn_id = roles["btn_id"]
            x, y = _place_aligned("ramo_row", 3 * k + 2, btn_id)
            node_by_id[btn_id]["position"] = {"x": x, "y": y}

    # ── Zona 2: reset + bobina, agrupados à DIREITA de toda a Zona 1 ─────
    zone1_cols = 3 * (n_atoms - 1) + 3  # última coluna usada + 1 (0-indexada)
    zone2_x0 = cyl_first_x + zone1_cols * ramo_cell_w + zone_gap

    grid.add_row("reset_row", zone2_cell_w, _M.relay_switch_height, reset_row_y,
                 x_origin=zone2_x0)
    grid.add_row("coil_row", zone2_cell_w, _M.solenoid_coil_height, coil_row_y,
                 x_origin=zone2_x0)

    for k in range(n_atoms):
        reset_id = _contact(f"{k}-reset_nc")
        x, y = grid.place("reset_row", k, reset_id)
        node_by_id[reset_id]["position"] = {"x": x, "y": y}

        coil_id = roles["coil_by_idx"][k]
        x, y = grid.place("coil_row", k, coil_id)
        node_by_id[coil_id]["position"] = {"x": x, "y": y}

    # ── Ground (barra horizontal, base da faixa elétrica) ────────────────
    ground_id = roles["ground_id"]
    node_by_id[ground_id]["position"] = {"x": cyl_first_x, "y": ground_row_y}

    # ── Filhos (Exhaust / PressureSource) posicionados relativo ao pai ───
    _CHILD_ANCHOR = {"Exhaust": "R", "PressureSource": "P"}
    child_parent: dict[str, tuple[str, str]] = {}
    for conn in data["connections"]:
        s_id, s_anc = conn["source"]["node"], conn["source"]["anchor"]
        t_id, t_anc = conn["target"]["node"], conn["target"]["anchor"]
        for child, parent, p_anc in [(s_id, t_id, t_anc), (t_id, s_id, s_anc)]:
            if node_type_map.get(child) in _CHILD_ANCHOR:
                child_parent.setdefault(child, (parent, p_anc))

    gap = 32
    for child_id, (parent_id, parent_anchor) in child_parent.items():
        parent_pos = node_by_id[parent_id]["position"]
        parent_local = _M.anchor_local.get(node_type_map[parent_id], {}).get(parent_anchor)
        if parent_local is None:
            node_by_id[child_id]["position"] = {"x": parent_pos["x"], "y": parent_pos["y"] + 100}
            continue
        anc_x = parent_pos["x"] + parent_local[0]
        anc_y = parent_pos["y"] + parent_local[1]
        child_type = node_type_map[child_id]
        child_local = _M.anchor_local.get(child_type, {}).get(_CHILD_ANCHOR[child_type])
        cx = anc_x - (child_local[0] if child_local else 0.0)
        cy = anc_y + gap
        node_by_id[child_id]["position"] = {"x": cx, "y": cy}

    # ── Limpeza final: remove _role de todos os nós ──────────────────────
    for node in data["nodes"]:
        node.pop("_role", None)

    # ── Roteamento A* (idêntico ao pneumático) ───────────────────────────
    from circuit_generator.astar_router import build_grid, route_connection, get_exit_dir

    def _scene_xy(node_id: str, anchor_name: str) -> tuple[float, float] | None:
        pos = node_by_id[node_id]["position"]
        ntype = node_type_map.get(node_id, "")
        if ntype == "VoltageSource" and anchor_name.startswith("X"):
            anchors = node_by_id[node_id]["properties"]["anchors"]
            idx = anchors.index(anchor_name)
            return (pos["x"] + _M.vsource_pix_w + idx * _M.pl_spacing,
                    pos["y"] + _M.vsource_pix_h * 69 / 100)
        if ntype == "Ground" and anchor_name.startswith("X"):
            anchors = node_by_id[node_id]["properties"]["anchors"]
            idx = anchors.index(anchor_name)
            return (pos["x"] + _M.ground_pix_w * 0.5 + idx * _M.pl_spacing, pos["y"])
        local = anchor_local_for_routing(ntype, anchor_name)
        return (pos["x"] + local[0], pos["y"] + local[1]) if local else (pos["x"], pos["y"])

    astar_grid = build_grid(data["nodes"])
    for conn in data.get("connections", []):
        s_id, s_anc = conn["source"]["node"], conn["source"]["anchor"]
        t_id, t_anc = conn["target"]["node"], conn["target"]["anchor"]
        spos = _scene_xy(s_id, s_anc)
        tpos = _scene_xy(t_id, t_anc)
        if spos is None or tpos is None:
            continue
        s_type, t_type = node_type_map.get(s_id, ""), node_type_map.get(t_id, "")
        wps = route_connection(astar_grid, spos, get_exit_dir(s_type, s_anc),
                                tpos, get_exit_dir(t_type, t_anc),
                                src_type=s_type, tgt_type=t_type,
                                src_id=s_id, tgt_id=t_id)
        if wps is not None:
            conn["waypoints"] = wps

    return data
