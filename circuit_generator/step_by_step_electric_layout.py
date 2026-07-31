"""
Posicionamento espacial do método passo a passo elétrico.

Recebe o dicionário de dados do circuito (com _role em cada nó, gerado por
circuit_generator.methods.step_by_step_electric) e preenche as posições x/y
de cada componente usando circuit_generator.grid_layout.Grid.

v1 -- ver docs/superpowers/specs/2026-07-30-step-by-step-electric-layout-design.md,
docs/superpowers/specs/2026-07-31-step-by-step-electric-power-contacts-design.md
e docs/superpowers/specs/2026-07-31-step-by-step-electric-layout-v1-design.md.

Diferente da v0: cada átomo agora é um BLOCO COESO (ramo A | ramo B no topo,
convergindo em reset+bobina K logo abaixo, tudo na mesma faixa de colunas)
-- não mais duas zonas distantes (ramo A/B numa ponta, reset+K na outra). A
zona de potência (Y), essa sim, continua agrupada à parte, à direita de
todos os blocos de átomo -- é ela que corresponde ao "reset+bobina fica
tudo junto no final" pedido no brainstorm original (mal-entendido
inicialmente como sendo sobre o bloco K, corrigido depois de ver o v0
renderizado).

Faixas verticais (topo -> base):
  1. Pistões/válvulas (cilindro + 4/2), uma coluna por letra.
  2. VoltageSource (barra horizontal).
  3. Bloco coeso por átomo: ramo A (col 3k) | ramo B (col 3k+1) | botão (col
     3k+2, só no último átomo) -- reset (NC) e bobina K empilhados logo
     abaixo, na MESMA coluna do ramo B (3k+1).
     Zona de potência (à DIREITA de todos os blocos de átomo, mesma faixa
     Y): 1 sub-coluna por (cilindro, direção) -- contato(s) de potência
     empilhados sobre a bobina Y correspondente.
  4. Ground (barra horizontal).

Reatribuição de anchor por proximidade (NOVO na v1, v0 deixava isso fora de
escopo): como só existe UMA VoltageSource e UMA Ground (não uma por átomo,
como a PressureLine do pneumático), a atribuição é mais simples que a
"Fase 3" de step_by_step_layout.py -- ordena as conexões de cada barra pela
posição X real do componente do outro lado e casa 1:1 com os anchors
ordenados por X, garantindo zero cruzamento por construção (mapeamento
monotônico), sem precisar de resolução de conflito por empurrão.
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

    # ── Config (v1: hardcoded, sem arquivo json externo) ─────────────────
    #
    #   cyl_cell_w subiu pra 1000 (era 300) -- pedido explícito do usuário
    #   depois de ver o v0 renderizado ("espaço entre os pistões, uns
    #   1000px").
    #
    #   vsource_row_y/ramo_row_y/ramo_stack_gap: a v0 tinha uma colisão real
    #   aqui -- vsource_row_y (700) coincidia EXATAMENTE com a primeira
    #   linha empilhada de sensores (ramo_row_y - 1*ramo_stack_gap =
    #   850-150 = 700), fazendo a barra da fonte se sobrepor ao primeiro
    #   contato de sensor de cada bloco. A v1 original "corrigiu" isso só
    #   para depth 1 (a distância de vsource até ramo_row -- 500px -- não é
    #   a distância até uma linha EMPILHADA, que fica cada vez mais perto
    #   de vsource conforme a profundidade do stack aumenta); com 3 eventos
    #   simultâneos num mesmo átomo (bloco paralelo com 3 ramos, ex.
    #   "(A+B+C+)A-B-C-"), a linha de profundidade 3 ainda colidia com a
    #   VoltageSource. ramo_row_y foi elevada para 1700 para que MESMO a
    #   profundidade 5 (bem além de qualquer caso realista) mantenha uma
    #   folga positiva em relação à base da VoltageSource:
    #     vsource ocupa y em [700, 700+vsource_pix_h] = [700, 800].
    #     linha de profundidade d ocupa y em
    #       [1700 - d*150, 1700 - d*150 + relay_switch_height] =
    #       [1700 - d*150, 1700 - d*150 + 75].
    #     d=1 -> [1550, 1625]  (folga de 750px até a base da vsource)
    #     d=2 -> [1400, 1475]  (folga de 600px)
    #     d=3 -> [1250, 1325]  (folga de 450px -- caso testado em
    #                           TestNoCollisionOrDuplicatePositions)
    #     d=4 -> [1100, 1175]  (folga de 300px)
    #     d=5 -> [ 950, 1025]  (folga de 150px)
    #     d=6 -> [ 800,  875]  (toca a base da vsource -- fora do range
    #                           defensivo que este layout garante; um
    #                           bloco paralelo com 6+ ramos simultâneos
    #                           não é um caso realista para este método).
    cyl_cell_w = 1000
    cyl_first_x = 0.0
    cyl_row_y = 0.0
    v42_row_y = 400.0
    vsource_row_y = 700.0
    ramo_row_y = 1700.0
    ramo_stack_gap = 150.0
    reset_gap = 150.0
    coil_gap = 150.0
    ground_gap = 300.0
    zone_gap = 400.0
    ramo_cell_w = 200.0
    zone3_cell_w = 200.0

    reset_row_y = ramo_row_y + reset_gap
    coil_row_y = reset_row_y + coil_gap
    ground_row_y = coil_row_y + ground_gap

    # ── Região de pistões/válvulas -- sem OrValve/pilot_sig no gerador
    #    elétrico, então sempre 1 coluna por letra ────────────────────────
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

    # ── Bloco coeso por átomo: ramo A | ramo B (topo) + reset/bobina K
    #    (logo abaixo, mesma coluna do ramo B) ─────────────────────────────
    grid.add_row("ramo_row", ramo_cell_w, _M.relay_switch_height, ramo_row_y,
                 x_origin=cyl_first_x)
    grid.add_row("reset_row", ramo_cell_w, _M.relay_switch_height, reset_row_y,
                 x_origin=cyl_first_x)
    grid.add_row("coil_row", ramo_cell_w, _M.relay_coil_height, coil_row_y,
                 x_origin=cyl_first_x)

    contact_by_role = roles["contact_by_role"]

    def _contact(role_key: str) -> str:
        return contact_by_role[role_key]

    stack_rows_added: set[str] = set()
    for k in range(n_atoms):
        # Ramo A: cadeia de contatos de sensor (i=0,1,...) + contato do K anterior.
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

        # Reset (NC) + bobina K: mesma coluna do ramo B (3k+1), logo abaixo
        # -- bloco coeso por átomo, não mais uma zona distante.
        reset_id = _contact(f"{k}-reset_nc")
        x, y = _place_aligned("reset_row", 3 * k + 1, reset_id)
        node_by_id[reset_id]["position"] = {"x": x, "y": y}

        coil_id = roles["coil_by_idx"][k]
        x, y = _place_aligned("coil_row", 3 * k + 1, coil_id)
        node_by_id[coil_id]["position"] = {"x": x, "y": y}

    # ── Zona de potência: contatos + bobina Y, agrupados à DIREITA de
    #    todos os blocos de átomo -- 1 sub-coluna por (cilindro, direção)
    #    presente na sequência, ordenada pelo primeiro átomo que dispara
    #    aquele movimento ─────────────────────────────────────────────────
    power_contacts_by_group = roles["power_contacts_by_group"]
    power_coil_by_group = roles["power_coil_by_group"]

    group_keys = sorted(
        power_contacts_by_group.keys(),
        key=lambda gk: min(k for k, _ in power_contacts_by_group[gk]),
    )

    zone_cols = 3 * (n_atoms - 1) + 3  # última coluna usada + 1 (0-indexada)
    zone3_x0 = cyl_first_x + zone_cols * ramo_cell_w + zone_gap

    power_stack_rows_added: set[str] = set()
    for g, group_key in enumerate(group_keys):
        contacts = sorted(power_contacts_by_group[group_key])  # ordena por k
        for depth, (_k, contact_id) in enumerate(contacts, start=1):
            row_id = f"power_row_{depth}"
            if row_id not in power_stack_rows_added:
                grid.add_row(row_id, zone3_cell_w, _M.relay_switch_height,
                             reset_row_y - depth * ramo_stack_gap, x_origin=zone3_x0)
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
    #    grid (cresce, nunca encolhe -- ver step_by_step_layout.py) ──────
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

    # ── Reatribuição de anchor por proximidade (VoltageSource/Ground) ────
    #
    #   O gerador atribui X1, X2, ... sequencialmente, sem noção de
    #   posição de tela -- isso produzia fios cruzados sem necessidade
    #   (Zona de potência, bem à direita, presa a um anchor cedo demais no
    #   array). Só existe UMA VoltageSource e UMA Ground (não uma por
    #   átomo, como a PressureLine do pneumático), então a atribuição é um
    #   mapeamento monotônico simples: ordena as conexões de cada barra
    #   pela posição X real do componente do outro lado, ordena os anchors
    #   por posição X, casa 1:1 -- garante ZERO cruzamento entre as
    #   próprias conexões da barra por construção (duas conexões nunca
    #   trocam de ordem relativa), sem precisar da lógica de conflito por
    #   empurrão que a PressureLine precisa (lá existem N linhas
    #   competindo pelo mesmo espaço X; aqui é uma barra só).
    def _bus_anchor_x(bus_id: str, anchor_name: str) -> float:
        pos = node_by_id[bus_id]["position"]
        anchors = node_by_id[bus_id]["properties"]["anchors"]
        idx = anchors.index(anchor_name)
        if node_type_map[bus_id] == "VoltageSource":
            return pos["x"] + _M.vsource_pix_w + idx * _M.pl_spacing
        return pos["x"] + _M.ground_pix_w * 0.5 + idx * _M.pl_spacing

    def _other_endpoint_x(node_id: str, anchor_name: str) -> float:
        pos = node_by_id[node_id]["position"]
        local = anchor_local_for_routing(node_type_map.get(node_id, ""), anchor_name)
        return pos["x"] + (local[0] if local else 0.0)

    def _select_spread_anchors(anchors_sorted: list[str], n: int) -> list[str]:
        """Escolhe n anchors dentre os m disponíveis (já ordenados por X
        real), espalhados proporcionalmente por TODO o alcance do array --
        não apenas o prefixo mais à esquerda.

        Achado de revisão: um zip(conns_sorted, anchors_sorted) ingênuo usa
        sempre os m anchors MAIS À ESQUERDA quando n < m (a barra é
        dimensionada para cobrir toda a largura do circuito -- ex. 58
        anchors -- mas só usa os primeiros n, ex. 13, deixando o resto do
        comprimento da barra sem uso e produzindo fios enormes até
        componentes distantes). Espalhar por índice proporcional
        (idx_i = round(i * (m-1) / (n-1))) resolve isso mantendo o mesmo
        mapeamento monotônico (i crescente -> idx crescente) -- quando
        n == m reduz exatamente ao mapeamento 1:1 anterior (idx_i == i).
        """
        m = len(anchors_sorted)
        if n <= 0:
            return []
        if n == 1:
            return [anchors_sorted[(m - 1) // 2]]
        indices: list[int] = []
        prev = -1
        for i in range(n):
            idx = round(i * (m - 1) / (n - 1))
            if idx <= prev:  # guarda contra colisão de arredondamento
                idx = prev + 1
            idx = min(idx, m - 1)
            indices.append(idx)
            prev = idx
        return [anchors_sorted[idx] for idx in indices]

    vsource_conns = [c for c in data["connections"] if c["source"]["node"] == vsource_id]
    ground_conns = [c for c in data["connections"] if c["target"]["node"] == ground_id]

    vsource_anchors_sorted = sorted(
        node_by_id[vsource_id]["properties"]["anchors"],
        key=lambda a: _bus_anchor_x(vsource_id, a),
    )
    vsource_conns_sorted = sorted(
        vsource_conns,
        key=lambda c: _other_endpoint_x(c["target"]["node"], c["target"]["anchor"]),
    )
    vsource_anchor_selection = _select_spread_anchors(vsource_anchors_sorted, len(vsource_conns_sorted))
    for conn, anchor_name in zip(vsource_conns_sorted, vsource_anchor_selection):
        conn["source"]["anchor"] = anchor_name

    ground_anchors_sorted = sorted(
        node_by_id[ground_id]["properties"]["anchors"],
        key=lambda a: _bus_anchor_x(ground_id, a),
    )
    ground_conns_sorted = sorted(
        ground_conns,
        key=lambda c: _other_endpoint_x(c["source"]["node"], c["source"]["anchor"]),
    )
    ground_anchor_selection = _select_spread_anchors(ground_anchors_sorted, len(ground_conns_sorted))
    for conn, anchor_name in zip(ground_conns_sorted, ground_anchor_selection):
        conn["target"]["anchor"] = anchor_name

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
