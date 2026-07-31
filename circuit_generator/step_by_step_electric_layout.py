"""
Posicionamento espacial do método passo a passo elétrico.

Recebe o dicionário de dados do circuito (com _role em cada nó, gerado por
circuit_generator.methods.step_by_step_electric) e preenche as posições x/y
de cada componente usando circuit_generator.grid_layout.Grid.

v0 -- ver docs/superpowers/specs/2026-07-30-step-by-step-electric-layout-design.md
e docs/superpowers/specs/2026-07-31-step-by-step-electric-power-contacts-design.md.
Reaproveita o ALGORITMO (não o código) da região de pistões/válvulas de
step_by_step_layout.py (pneumático) -- mesmo _role scheme
(cylinder:{letra}, main_valve:{letra}).

Diferente de uma versão anterior deste arquivo: o gerador elétrico não usa
mais OrValve/pilot_sig pra multi-ciclo (substituído por contatos de
potência em paralelo, ver o gerador) -- a região de pistões/válvulas volta
a reservar sempre 1 coluna por cilindro, sem lógica de cadeia.

Faixas verticais (topo -> base):
  1. Pistões/válvulas (cilindro + 4/2), uma coluna por letra.
  2. VoltageSource (barra horizontal).
  3. Zona 1 (esquerda): bloco por átomo -- ramo A | ramo B | botão (só no
     último átomo).
     Zona 2 (à DIREITA de toda a Zona 1, mesma faixa Y): reset (NC)
     empilhado sobre a bobina K_k, um bloco denso por átomo.
     Zona 3 (à DIREITA de toda a Zona 2, mesma faixa Y): 1 sub-coluna por
     (cilindro, direção) presente na sequência -- contato(s) de potência
     empilhados (1 por átomo que dispara aquele movimento, mais linhas se
     multi-ciclo) sobre a bobina Y correspondente.
  4. Ground (barra horizontal).

Fora de escopo (v0, confirmado com o usuário): reatribuição de anchor da
VoltageSource/Ground por proximidade real de tela -- os anchors renderizam
na ordem sequencial que a topologia já atribuiu (next_bus_anchor()).
"""

import math

from circuit_generator.grid_layout import Grid
from circuit_generator.sprite_metrics import METRICS as _M, anchor_local_for_routing


def _build_role_maps(data: dict) -> dict:
    role_map = {n["id"]: n.get("_role", "") for n in data["nodes"]}

    cyl_by_letter: dict[str, str] = {}
    v42_by_letter: dict[str, str] = {}
    coil_by_idx: dict[int, str] = {}
    contact_by_role: dict[str, str] = {}
    power_coil_by_group: dict[tuple[str, str], str] = {}
    vsource_id: str | None = None
    ground_id: str | None = None
    btn_id: str | None = None

    for nid, role in role_map.items():
        if role.startswith("cylinder:"):
            cyl_by_letter[role.split(":", 1)[1]] = nid
        elif role.startswith("main_valve:"):
            v42_by_letter[role.split(":", 1)[1]] = nid
        elif role.startswith("power_coil:"):
            _, letter, direction = role.split(":")
            dir_tag = "ext" if direction == "+" else "ret"
            power_coil_by_group[(letter, dir_tag)] = nid
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

    # Contatos de potência (role "contact:power-{letra}-{dir_tag}-{k}") --
    # agrupados por (letra, dir_tag), cada grupo é a lista de (k, node_id)
    # que alimenta em paralelo a mesma bobina Y daquele grupo.
    power_contacts_by_group: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for role_key, nid in contact_by_role.items():
        if role_key.startswith("power-"):
            _, letter, dir_tag, k_str = role_key.split("-")
            power_contacts_by_group.setdefault((letter, dir_tag), []).append((int(k_str), nid))

    return {
        "role_map":                role_map,
        "cyl_by_letter":           cyl_by_letter,
        "v42_by_letter":           v42_by_letter,
        "coil_by_idx":             coil_by_idx,
        "contact_by_role":         contact_by_role,
        "power_coil_by_group":     power_coil_by_group,
        "power_contacts_by_group": power_contacts_by_group,
        "vsource_id":              vsource_id,
        "ground_id":               ground_id,
        "btn_id":                  btn_id,
        "n_atoms":                 len(coil_by_idx),
    }


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
    vsource_row_y = 700.0
    ramo_row_y = 850.0
    ramo_stack_gap = 150.0
    zone_gap = 400.0
    reset_row_y = ramo_row_y
    coil_row_y = ramo_row_y + 150.0
    ground_row_y = coil_row_y + 300.0
    ramo_cell_w = 200.0
    zone2_cell_w = 200.0
    zone3_cell_w = 200.0

    # ── Região de pistões/válvulas -- sem OrValve/pilot_sig no gerador
    #    elétrico (multi-ciclo agora é resolvido por contatos de potência
    #    em paralelo, seção de Zona 3), então sempre 1 coluna por letra ──
    letters = sorted(roles["cyl_by_letter"])
    cyl_col: dict[str, int] = {letter: i for i, letter in enumerate(letters)}

    grid.add_row("cylinder", cyl_cell_w, _M.cyl_height, cyl_row_y, x_origin=cyl_first_x)
    grid.add_row("main_valve", cyl_cell_w, _M.v42_height, v42_row_y, x_origin=cyl_first_x)

    for letter in letters:
        cyl_id = roles["cyl_by_letter"][letter]
        v42_id = roles["v42_by_letter"][letter]
        x, y = grid.place("cylinder", cyl_col[letter], cyl_id)
        node_by_id[cyl_id]["position"] = {"x": x, "y": y}
        x, y = grid.place("main_valve", cyl_col[letter], v42_id)
        node_by_id[v42_id]["position"] = {"x": x, "y": y}

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
        # Ramo A: cadeia de contatos de sensor (i=0,1,...) + contato do K anterior.
        # A ordem da cadeia é a ORDEM DE CRIAÇÃO em step_by_step_electric.py
        # (0-indexada, i crescente) -- empilha pra CIMA (y decrescente),
        # ficando o contato do K anterior sempre na linha-base (ramo_row).
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

        # Ramo B: self-hold do próprio K_k.
        self_id = _contact(f"{k}-ramo_b_self")
        x, y = _place_aligned("ramo_row", 3 * k + 1, self_id)
        node_by_id[self_id]["position"] = {"x": x, "y": y}

        # Botão de bootstrap: só o último átomo.
        if k == n_atoms - 1:
            btn_id = roles["btn_id"]
            x, y = _place_aligned("ramo_row", 3 * k + 2, btn_id)
            node_by_id[btn_id]["position"] = {"x": x, "y": y}

    # ── Zona 2: reset + bobina do anel, agrupados à DIREITA de toda a
    #    Zona 1 ────────────────────────────────────────────────────────
    zone1_cols = 3 * (n_atoms - 1) + 3  # última coluna usada + 1 (0-indexada)
    zone2_x0 = cyl_first_x + zone1_cols * ramo_cell_w + zone_gap

    grid.add_row("reset_row", zone2_cell_w, _M.relay_switch_height, reset_row_y,
                 x_origin=zone2_x0)
    grid.add_row("coil_row", zone2_cell_w, _M.relay_coil_height, coil_row_y,
                 x_origin=zone2_x0)

    for k in range(n_atoms):
        reset_id = _contact(f"{k}-reset_nc")
        x, y = grid.place("reset_row", k, reset_id)
        node_by_id[reset_id]["position"] = {"x": x, "y": y}

        coil_id = roles["coil_by_idx"][k]
        x, y = grid.place("coil_row", k, coil_id)
        node_by_id[coil_id]["position"] = {"x": x, "y": y}

    # ── Zona 3: contatos de potência + bobina Y, agrupados à DIREITA de
    #    toda a Zona 2 -- 1 sub-coluna por (cilindro, direção) presente na
    #    sequência, ordenada pelo primeiro átomo que dispara aquele
    #    movimento (determinístico, não depende de ordem de dict) ───────
    power_contacts_by_group = roles["power_contacts_by_group"]
    power_coil_by_group = roles["power_coil_by_group"]

    group_keys = sorted(
        power_contacts_by_group.keys(),
        key=lambda gk: min(k for k, _ in power_contacts_by_group[gk]),
    )

    zone3_x0 = zone2_x0 + n_atoms * zone2_cell_w + zone_gap

    power_stack_rows_added: set[str] = set()
    for g, group_key in enumerate(group_keys):
        contacts = sorted(power_contacts_by_group[group_key])  # ordena por k
        for depth, (_k, contact_id) in enumerate(contacts, start=1):
            row_id = f"power_row_{depth}"
            if row_id not in power_stack_rows_added:
                grid.add_row(row_id, zone3_cell_w, _M.relay_switch_height,
                             reset_row_y - (depth - 1) * ramo_stack_gap, x_origin=zone3_x0)
                power_stack_rows_added.add(row_id)
            if depth == 1:
                x, y = grid.place(row_id, g, contact_id)
            else:
                x, y = _place_aligned(row_id, g, contact_id)
            node_by_id[contact_id]["position"] = {"x": x, "y": y}

        coil_id = power_coil_by_group[group_key]
        if "power_coil_row" not in power_stack_rows_added:
            grid.add_row("power_coil_row", zone3_cell_w, _M.solenoid_coil_height,
                         coil_row_y, x_origin=zone3_x0)
            power_stack_rows_added.add("power_coil_row")
        x, y = grid.place("power_coil_row", g, coil_id)
        node_by_id[coil_id]["position"] = {"x": x, "y": y}

    # ── Ground (barra horizontal, base da faixa elétrica) ────────────────
    ground_id = roles["ground_id"]
    node_by_id[ground_id]["position"] = {"x": cyl_first_x, "y": ground_row_y}

    # ── Dimensiona as barras VoltageSource/Ground pelo alcance real do
    #    grid ──────────────────────────────────────────────────────────
    #
    #   step_by_step_electric.py não tem nenhuma posição de tela real pra
    #   decidir quantos anchors a barra precisa -- só quem sabe é esta
    #   etapa, via Grid (que já posicionou toda a região de pistões/
    #   válvulas/lógica/potência acima). Cresce (nunca encolhe) o array de
    #   anchors pra cobrir o alcance físico real do circuito -- mesma
    #   ideia do dimensionamento de PressureLine em step_by_step_layout.py
    #   ("Dimensiona as PressureLines pelo alcance real do grid"), mas mais
    #   simples: há só UMA VoltageSource e UMA Ground no total, e ambas já
    #   nascem na borda esquerda do circuito (cyl_first_x) -- só é preciso
    #   crescer pra DIREITA, apendando novos anchors ao final da lista
    #   (nunca renumerando os existentes, já referenciados por índice em
    #   conexões antigas).
    x_range = grid.occupied_x_range()
    if x_range is not None:
        min_x, max_x = x_range
        needed_count = max(1, math.ceil((max_x - min_x) / _M.pl_spacing) + 1)
        for bus_id in (vsource_id, ground_id):
            anchors = node_by_id[bus_id]["properties"]["anchors"]
            next_idx = max((int(a[1:]) for a in anchors), default=0) + 1
            while len(anchors) < needed_count:
                anchors.append(f"X{next_idx}")
                next_idx += 1

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
        # anchor_local_for_routing (não METRICS.anchor_local puro) -- é essa
        # função que o A* usa mais abaixo (_scene_xy) pra calcular o ponto
        # real de roteamento do anchor "P" de Valve_3_2_Ways/Valve_4_2_Ways
        # (soma pilot_side_offset_x, ver sprite_metrics.anchor_local_for_routing).
        parent_local = anchor_local_for_routing(node_type_map[parent_id], parent_anchor)
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
