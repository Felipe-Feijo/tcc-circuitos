"""Testes para circuit_generator/step_by_step_layout.py — ver
docs/superpowers/specs/2026-07-11-step-by-step-positioning-design.md
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.sequence_parser import parse
from circuit_generator.methods import step_by_step_pneumatic
from circuit_generator import step_by_step_layout as layout


def _node(data, node_id):
    return next(n for n in data["nodes"] if n["id"] == node_id)


def _obstacle_rect(node_by_id, node_id):
    """Retângulo (x0, y0, x1, y1) do sprite de node_id, pra checagem de
    cruzamento geométrico -- usa SPRITE_SIZES (0,0) se o tipo não tiver
    tamanho conhecido."""
    from circuit_generator.astar_router import SPRITE_SIZES
    n = node_by_id[node_id]
    w, h = SPRITE_SIZES.get(n["type"], (0, 0))
    x, y = n["position"]["x"], n["position"]["y"]
    return (x, y, x + w, y + h)


def _anchor_xy(node_by_id, node_id, anchor_name):
    """Posição real (x, y) de um anchor, pra checagem geométrica -- trata
    anchors "Xi" de PressureLine à parte porque layout_anchors() (ver
    step_by_step_layout._pl_anchor_x) posiciona pelo índice na lista, não
    pelo número no nome."""
    from circuit_generator.sprite_metrics import METRICS as _M, anchor_local_for_routing
    n = node_by_id[node_id]
    pos = n["position"]
    if n["type"] == "PressureLine" and anchor_name.startswith("X"):
        idx = int(anchor_name[1:])
        return (pos["x"] + _pl_anchor_x_offset(idx, n["properties"]["anchors"]), pos["y"] + _M.pl_pix_h)
    local = anchor_local_for_routing(n["type"], anchor_name)
    return (pos["x"] + local[0], pos["y"] + local[1]) if local else (pos["x"], pos["y"])


def _seg_crosses_rect(p1, p2, r):
    """True se o segmento ortogonal p1->p2 atravessa o interior do
    retângulo r. Só reconhece segmentos puramente verticais ou
    horizontais -- um segmento diagonal nunca é considerado cruzamento
    (não deveria existir num waypoint ortogonal, mas não trava o teste
    silenciosamente tratando-o como horizontal)."""
    x0, y0, x1, y1 = r
    if abs(p1[0] - p2[0]) < 0.01:
        x = p1[0]
        ylo, yhi = sorted([p1[1], p2[1]])
        return x0 < x < x1 and not (yhi < y0 or ylo > y1)
    if abs(p1[1] - p2[1]) < 0.01:
        y = p1[1]
        xlo, xhi = sorted([p1[0], p2[0]])
        return y0 < y < y1 and not (xhi < x0 or xlo > x1)
    return False


class TestRoleAndConnectionMaps:
    def test_role_maps_extract_cylinders_v42_pl_memory(self):
        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        roles = layout._build_role_maps(data)
        assert roles["cyl_by_letter"] == {"A": "gen-cyl-A", "B": "gen-cyl-B"}
        assert roles["v42_by_letter"] == {"A": "gen-v42-A", "B": "gen-v42-B"}
        assert roles["pl_by_idx"] == {0: "gen-pl-step0", 1: "gen-pl-step1",
                                       2: "gen-pl-step2", 3: "gen-pl-step3"}
        assert roles["mc_by_idx"] == {0: "gen-mc-0", 1: "gen-mc-1",
                                       2: "gen-mc-2", 3: "gen-mc-3"}
        assert roles["btn_id"] == "gen-btn"
        assert roles["n_atoms"] == 4


class TestPistonValveRegion:
    def test_cylinders_and_v42_positioned_same_column_per_letter(self):
        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        cyl_a = _node(result, "gen-cyl-A")
        v42_a = _node(result, "gen-v42-A")
        assert cyl_a["position"]["x"] == v42_a["position"]["x"]
        assert cyl_a["position"]["y"] != v42_a["position"]["y"]

    def test_different_letters_get_different_columns(self):
        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        cyl_a = _node(result, "gen-cyl-A")
        cyl_b = _node(result, "gen-cyl-B")
        assert cyl_a["position"]["x"] != cyl_b["position"]["x"]

    def test_column_gap_between_cylinders_is_sum_of_reserved_columns(self):
        # Cada letra reserva 1 coluna à esquerda (lado PL) e 1 à direita
        # (lado PR) no mínimo -- sem repetição (caso de "A+B+A-B-"), o
        # espaço entre A e B é 1 (direita de A) + 1 (esquerda de B) + o
        # próprio cilindro de A = 3 * group_gap, não 2 como antes (ver
        # docs/superpowers/specs/2026-07-12-step-by-step-multi-cycle-or-valve-design.md).
        import json
        cfg = json.loads(layout._CONFIG_PATH.read_text(encoding="utf-8"))
        group_gap = cfg["columns"]["group_gap"]

        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        cyl_a = _node(result, "gen-cyl-A")
        cyl_b = _node(result, "gen-cyl-B")

        assert cyl_b["position"]["x"] - cyl_a["position"]["x"] == 3 * group_gap

    def test_repeated_cylinder_reserves_extra_columns_for_its_or_chain(self):
        # "A+B+A-A+B-A-": A+ e A- ocorrem 2x cada -> 1 OrValve por lado ->
        # reserva 1 coluna de cada lado de A igual ao caso sem repetição
        # (max(1, 2-1) == 1) -- não testa nada novo por si só, mas
        # "A+A-A+A-A+A-" (3x cada) reserva max(1, 3-1) == 2 colunas de
        # cada lado, o dobro do mínimo.
        import json
        cfg = json.loads(layout._CONFIG_PATH.read_text(encoding="utf-8"))
        group_gap = cfg["columns"]["group_gap"]

        data = step_by_step_pneumatic.generate(parse("A+A-A+A-A+A-B+B-"))
        result = layout.apply(data)
        cyl_a = _node(result, "gen-cyl-A")
        cyl_b = _node(result, "gen-cyl-B")

        # A reserva 2 colunas à direita (PR, 3 ocorrências de "-"), B
        # reserva 1 coluna à esquerda (PL, mínimo) -> 2 + 1 + 1 (o próprio
        # cilindro A) = 4 colunas de distância.
        assert cyl_b["position"]["x"] - cyl_a["position"]["x"] == 4 * group_gap

    def test_cylinder_row_above_main_valve_row(self):
        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        cyl_a = _node(result, "gen-cyl-A")
        v42_a = _node(result, "gen-v42-A")
        assert cyl_a["position"]["y"] < v42_a["position"]["y"]


class TestConfirmationChains:
    def test_simple_sequence_all_chains_have_one_sig(self):
        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        roles = layout._build_role_maps(data)
        chains = layout._build_confirmation_chains(data, roles)
        # 3 memórias (1,2,3) + 1 fechamento (btn) = 4 cadeias, 1 sig cada
        assert len(chains) == 4
        for target, sig_chain in chains.items():
            assert len(sig_chain) == 1

    def test_parallel_block_chain_has_two_sigs_in_order(self):
        data = step_by_step_pneumatic.generate(parse("C+(A+B+)C-A-B-"))
        roles = layout._build_role_maps(data)
        chains = layout._build_confirmation_chains(data, roles)
        # a cadeia que alimenta gen-mc-2 vem do bloco (A+B+) -- 2 sigs
        chain = chains[roles["mc_by_idx"][2]]
        assert chain == ["gen-sig-A-ext-1", "gen-sig-B-ext-2"]

    def test_closure_chain_targets_button(self):
        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        roles = layout._build_role_maps(data)
        chains = layout._build_confirmation_chains(data, roles)
        assert roles["btn_id"] in chains
        assert chains[roles["btn_id"]] == ["gen-sig-B-ret-3"]


class TestLogicRegion:
    def test_button_follows_the_same_diagonal_as_other_relays(self):
        # O botão segue a MESMA regra diagonal geral de qualquer par
        # Válvula1/Válvula2 (1 coluna à esquerda, 1 linha abaixo de quem
        # alimenta): é a "Válvula 1" de MC_0. A sig de fechamento NÃO
        # forma outro degrau diagonal -- está EM SÉRIE com o botão, então
        # fica na MESMA coluna dele, 1 linha abaixo (ver
        # test_closure_chain_tail_stacks_vertically_same_column).
        import json
        cfg = json.loads(layout._CONFIG_PATH.read_text(encoding="utf-8"))
        logic_cell_w = cfg["columns"]["logic_cell_width"]
        row_gap      = cfg["rows"]["logic_row_gap"]

        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        mc0 = _node(result, "gen-mc-0")
        btn = _node(result, "gen-btn")
        closure_sig = _node(result, "gen-sig-B-ret-3")

        assert btn["position"]["x"] == mc0["position"]["x"] - logic_cell_w
        assert btn["position"]["y"] == mc0["position"]["y"] + row_gap
        assert closure_sig["position"]["x"] == btn["position"]["x"]
        assert closure_sig["position"]["y"] == btn["position"]["y"] + row_gap

    def test_relay_sig_one_column_left_of_its_memory(self):
        import json
        cfg = json.loads(layout._CONFIG_PATH.read_text(encoding="utf-8"))
        logic_cell_w = cfg["columns"]["logic_cell_width"]
        row_gap      = cfg["rows"]["logic_row_gap"]

        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        mc1 = _node(result, "gen-mc-1")
        sig  = _node(result, "gen-sig-A-ext-0")  # confirma átomo 0, seta MC_1
        assert sig["position"]["x"] == mc1["position"]["x"] - logic_cell_w
        assert sig["position"]["y"] == mc1["position"]["y"] + row_gap

    def test_relay_column_is_dedicated_not_shared_with_previous_atom_memory(self):
        # Cada átomo ocupa 2 colunas dedicadas (memória + relay), sem
        # reaproveitar a coluna da memória do átomo anterior -- ver spec
        # "cada átomo k ocupa a coluna M + 2k". A relay do átomo 1
        # (confirma átomo 0, seta MC_1) NÃO pode cair na mesma coluna de
        # MC_0 -- precisa da sua própria coluna, entre MC_0 e MC_1.
        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        mc0 = _node(result, "gen-mc-0")
        relay_for_mc1 = _node(result, "gen-sig-A-ext-0")
        assert relay_for_mc1["position"]["x"] != mc0["position"]["x"]

    def test_parallel_chain_stacks_vertically_same_column(self):
        data = step_by_step_pneumatic.generate(parse("C+(A+B+)C-A-B-"))
        result = layout.apply(data)
        sig_a = _node(result, "gen-sig-A-ext-1")
        sig_b = _node(result, "gen-sig-B-ext-2")
        assert sig_a["position"]["x"] == sig_b["position"]["x"]
        assert sig_a["position"]["y"] != sig_b["position"]["y"]

    def test_closure_chain_tail_stacks_vertically_same_column(self):
        # último átomo é um bloco paralelo -- fechamento tem 2 sigs em série.
        # A cadeia inteira (sig0 = closure_row, sig1 = cauda) fica na
        # MESMA coluna do botão -- está em série com ele, não forma outro
        # degrau diagonal (ver test_button_follows_the_same_diagonal_as_other_relays).
        # Só mc0 -> btn é diagonal.
        data = step_by_step_pneumatic.generate(parse("A+B+(A-B-)"))
        result = layout.apply(data)
        mc0 = _node(result, "gen-mc-0")
        btn = _node(result, "gen-btn")
        sig0 = _node(result, "gen-sig-A-ret-2")
        sig1 = _node(result, "gen-sig-B-ret-3")

        assert sig0["position"] != {"x": 0, "y": 0}
        assert sig1["position"] != {"x": 0, "y": 0}
        assert mc0["position"]["x"] != btn["position"]["x"]
        assert btn["position"]["x"] == sig0["position"]["x"] == sig1["position"]["x"]
        assert sig0["position"]["y"] != sig1["position"]["y"]

    def test_no_two_nodes_share_the_same_position(self):
        data = step_by_step_pneumatic.generate(parse("C+(A+B+)C-A-B-"))
        result = layout.apply(data)
        positions = [(n["position"]["x"], n["position"]["y"]) for n in result["nodes"]
                     if n["type"] in ("Valve_3_2_Ways", "PressureLine")]
        assert len(positions) == len(set(positions))

    def test_no_two_nodes_share_the_same_position_all_node_types(self):
        """Every node in the generated circuit -- including Exhaust,
        PressureSource, DoubleActingCylinder and Valve_4_2_Ways, not just
        Valve_3_2_Ways/PressureLine -- must end up at a distinct (x, y).
        A collision here means two sprites would render stacked on top of
        each other in the canvas."""
        data = step_by_step_pneumatic.generate(parse("C+(A+B+)C-A-B-"))
        result = layout.apply(data)
        positions = [(n["id"], n["position"]["x"], n["position"]["y"]) for n in result["nodes"]]
        coords = [(x, y) for _, x, y in positions]
        if len(coords) != len(set(coords)):
            seen: dict[tuple[float, float], str] = {}
            dupes = []
            for nid, x, y in positions:
                if (x, y) in seen:
                    dupes.append((seen[(x, y)], nid, (x, y)))
                else:
                    seen[(x, y)] = nid
            raise AssertionError(f"duplicate positions found: {dupes}")


class TestChildPositioning:
    def test_every_node_has_role_removed(self):
        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        assert all("_role" not in n for n in result["nodes"])

    def test_exhaust_and_pressure_source_positioned_near_parent(self):
        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        v42_a = _node(result, "gen-v42-A")
        exh_ids = [c["source"]["node"] for c in result["connections"]
                   if c["target"]["node"] == "gen-v42-A" and c["target"]["anchor"] == "P"]
        assert len(exh_ids) == 1
        exhaust = _node(result, exh_ids[0])
        assert exhaust["type"] == "Exhaust"
        assert abs(exhaust["position"]["x"] - v42_a["position"]["x"]) < 500
        assert abs(exhaust["position"]["y"] - v42_a["position"]["y"]) < 500

    def test_no_node_left_at_origin_by_accident(self):
        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        at_origin = [n["id"] for n in result["nodes"]
                     if n["position"]["x"] == 0 and n["position"]["y"] == 0]
        assert at_origin == []


class TestRouting:
    def test_connections_get_waypoints(self):
        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        with_waypoints = [c for c in result["connections"] if "waypoints" in c]
        assert len(with_waypoints) > 0

    def test_pl_anchor_connections_get_waypoints_too(self):
        """PL-touching connections need explicit `waypoints` UNLESS the
        connection is already near-straight (dx below astar_router's
        `< 3px` "no routing needed" shortcut) -- proximity-based anchor
        assignment (see step_by_step_layout._nearest_pl_anchor) can pick an
        anchor whose x lands within a pixel or two of the target's x, in
        which case a straight vertical line *is* the correct route and the
        router legitimately returns None instead of a waypoints list.
        Connections whose endpoints are NOT nearly aligned in x must still
        be routed -- if the router silently stopped routing those, this
        assertion should catch it."""
        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        pl_conns = [c for c in result["connections"]
                    if c["source"]["anchor"].startswith("X") or c["target"]["anchor"].startswith("X")]
        assert len(pl_conns) > 0

        from circuit_generator.sprite_metrics import anchor_local_for_routing

        nodes_by_id = {n["id"]: n for n in result["nodes"]}
        node_type_map = {n["id"]: n["type"] for n in result["nodes"]}

        def _pl_anchor_xy_raw(node_id: str, anchor: str) -> tuple[float, float]:
            # Como _anchor_xy (módulo), mas SEM o offset pl_pix_h em y --
            # este teste só compara dx/dy contra STRAIGHT_THRESHOLD_PX pra
            # decidir se a conexão precisa de roteamento, não a posição
            # exata renderizada.
            node = nodes_by_id[node_id]
            x = node["position"]["x"]
            y = node["position"]["y"]
            if node["type"] == "PressureLine" and anchor.startswith("X"):
                idx = int(anchor[1:])
                return (x + _pl_anchor_x_offset(idx, node["properties"]["anchors"]), y)
            local = anchor_local_for_routing(node_type_map[node_id], anchor)
            return (x + local[0], y + local[1]) if local else (x, y)

        STRAIGHT_THRESHOLD_PX = 3  # mirrors astar_router.route_connection's shortcut

        needs_routing = []
        for c in pl_conns:
            sx, sy = _pl_anchor_xy_raw(c["source"]["node"], c["source"]["anchor"])
            tx, ty = _pl_anchor_xy_raw(c["target"]["node"], c["target"]["anchor"])
            # A* router skips routing if either dx < 3 OR dy < 3 (straight line).
            # So connections only need routing if both dx >= 3 AND dy >= 3.
            if abs(sx - tx) >= STRAIGHT_THRESHOLD_PX and abs(sy - ty) >= STRAIGHT_THRESHOLD_PX:
                needs_routing.append(c)

        # Sanity check: this fixture must actually exercise both branches,
        # otherwise the assertion below would be vacuous.
        assert len(needs_routing) > 0
        assert len(needs_routing) < len(pl_conns)

        assert all("waypoints" in c for c in needs_routing)


class TestLogicRegionColumnSpacing:
    """logic_cell_width precisa deixar folga suficiente pro retângulo de
    bloqueio do A* de uma Valve_3_2_Ways (444px de sprite + 80px de
    margem de cada lado, ver astar_router.py) não se sobrepor ao da
    coluna adjacente -- mesma classe de problema já corrigida pra
    group_gap na região de pistões (Task 4)."""

    def test_logic_cell_width_clears_valve_blocking_rect_with_margin(self):
        import json
        from circuit_generator.astar_router import SPRITE_SIZES
        cfg = json.loads(layout._CONFIG_PATH.read_text(encoding="utf-8"))
        logic_cell_w = cfg["columns"]["logic_cell_width"]
        v32_w, _ = SPRITE_SIZES["Valve_3_2_Ways"]
        MH = 80  # margem horizontal aplicada pelo astar_router pra válvulas
        blocked_w = v32_w + 2 * MH
        # folga mínima exigida entre colunas adjacentes -- não só "não
        # sobrepor" (folga > 0), mas uma folga real e generosa.
        assert logic_cell_w - blocked_w >= 300

    def test_relay_and_adjacent_memory_dont_overlap(self):
        # C+(A+B+)C-A-B-: MC_2 tem relay de 2 níveis (bloco paralelo),
        # bom caso de estresse pra colunas adjacentes.
        from circuit_generator.astar_router import SPRITE_SIZES
        v32_w, v32_h = SPRITE_SIZES["Valve_3_2_Ways"]
        MH = 80

        data = step_by_step_pneumatic.generate(parse("C+(A+B+)C-A-B-"))
        result = layout.apply(data)
        valve_nodes = [n for n in result["nodes"] if n["type"] == "Valve_3_2_Ways"]

        def blocked_rect(n):
            x, y = n["position"]["x"], n["position"]["y"]
            return (x - MH, y, x + v32_w + MH, y + v32_h)

        def overlap(r1, r2):
            return not (r1[2] <= r2[0] or r2[2] <= r1[0] or r1[3] <= r2[1] or r2[3] <= r1[1])

        for i, a in enumerate(valve_nodes):
            for b in valve_nodes[i + 1:]:
                assert not overlap(blocked_rect(a), blocked_rect(b)), (
                    f"{a['id']} e {b['id']} têm retângulos de bloqueio sobrepostos")


class TestAnchorAssignmentByProximity:
    def test_no_two_different_owners_share_the_same_pl_anchor(self):
        # Verifica que, depois de apply(), nenhum anchor de PL é
        # referenciado por 2 conexões cujo "outro lado" são componentes
        # DIFERENTES -- isso indicaria colisão não resolvida.
        data = step_by_step_pneumatic.generate(parse("C+(A+B+)C-A-B-"))
        result = layout.apply(data)
        pl_ids = {n["id"] for n in result["nodes"] if n["type"] == "PressureLine"}
        seen: dict[tuple, set] = {}
        for c in result["connections"]:
            for side, other in ((c["source"], c["target"]), (c["target"], c["source"])):
                if side["node"] in pl_ids and side["anchor"].startswith("X"):
                    key = (side["node"], side["anchor"])
                    seen.setdefault(key, set()).add(other["node"])
        collisions = {k: v for k, v in seen.items() if len(v) > 1}
        assert collisions == {}, f"anchors com múltiplos donos: {collisions}"

    def test_pilot_connections_are_assigned_the_nearest_anchor(self):
        # gen-pl-step0 alimenta gen-v42-A.PL -- o anchor escolhido deve
        # ser o mais próximo (ou empatado) da posição X REAL do anchor PL
        # de gen-v42-A (posição do nó + offset de anchor_local_for_routing,
        # não a posição crua do nó -- ver sprite_metrics.py) entre todos
        # os anchors da linha que ficam à esquerda do alvo (a conexão PL
        # sempre entra pela esquerda por design, ver _nearest_pl_anchor
        # side="left").
        from circuit_generator.sprite_metrics import anchor_local_for_routing

        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        pl0 = next(n for n in result["nodes"] if n["id"] == "gen-pl-step0")
        v42a = next(n for n in result["nodes"] if n["id"] == "gen-v42-A")
        conn = next(c for c in result["connections"]
                    if c["source"]["node"] == "gen-pl-step0" and c["target"]["node"] == "gen-v42-A"
                    and c["target"]["anchor"] == "PL")
        chosen_idx = int(conn["source"]["anchor"][1:])
        chosen_x = pl0["position"]["x"] + _pl_anchor_x_offset(chosen_idx, pl0["properties"]["anchors"])
        local = anchor_local_for_routing("Valve_4_2_Ways", "PL")
        target_x = v42a["position"]["x"] + (local[0] if local else 0)
        # nenhum outro anchor à esquerda do alvo pode estar estritamente mais perto
        for a in pl0["properties"]["anchors"]:
            idx = int(a[1:])
            ax = pl0["position"]["x"] + _pl_anchor_x_offset(idx, pl0["properties"]["anchors"])
            if ax >= target_x:
                continue
            assert abs(ax - target_x) >= abs(chosen_x - target_x) - 1e-6


def _pl_anchor_x_offset(idx, anchors):
    # PressureLine.layout_anchors() posiciona pelo índice na lista, não
    # pelo número do nome -- usa a origem real (menor índice atual) do
    # array, não a constante 1 (ver mesma ressalva em _pl_anchor_x,
    # circuit_generator/step_by_step_layout.py).
    from circuit_generator.sprite_metrics import METRICS as _M
    list_origin = min(int(a[1:]) for a in anchors)
    return _M.pl_pix_w / 2 + (idx - list_origin) * _M.pl_spacing


class TestGlobalPruning:
    def test_all_pressure_lines_share_the_same_anchor_count(self):
        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        counts = {len(n["properties"]["anchors"]) for n in result["nodes"]
                  if n["type"] == "PressureLine"}
        assert len(counts) == 1, f"larguras diferentes entre linhas: {counts}"

    def test_no_pl_anchor_connection_references_a_pruned_anchor(self):
        data = step_by_step_pneumatic.generate(parse("C+(A+B+)C-A-B-"))
        result = layout.apply(data)
        pl_by_id = {n["id"]: n for n in result["nodes"] if n["type"] == "PressureLine"}
        for c in result["connections"]:
            for side in (c["source"], c["target"]):
                if side["node"] in pl_by_id and side["anchor"].startswith("X"):
                    kept = {int(a[1:]) for a in pl_by_id[side["node"]]["properties"]["anchors"]}
                    assert int(side["anchor"][1:]) in kept


class TestPressureLineReachesEveryTarget:
    def test_pr_anchor_lands_right_of_target_even_with_many_cylinders_few_atoms(self):
        # Regressão do bug original: 16 cilindros agrupados em só 2 átomos
        # paralelos grandes (extensão simultânea, depois retração
        # simultânea) -- n_atoms pequeno, mas a região de válvulas 4/2 é
        # LARGA (16 colunas). Antes da correção, o orçamento de anchors
        # (baseado só em n_atoms) não alcançava as últimas colunas, e o
        # fallback de _nearest_pl_anchor silenciosamente devolvia um
        # anchor à ESQUERDA do alvo mesmo pedindo side="right".
        import string

        letters = list(string.ascii_uppercase[:16])
        events = [(l, "+", "ext") for l in letters] + [(l, "-", "ret") for l in letters]
        data = step_by_step_pneumatic.generate(events)
        result = layout.apply(data)
        nodes_by_id = {n["id"]: n for n in result["nodes"]}

        def anchor_x(pl_node, anchor_name):
            idx = int(anchor_name[1:])
            return pl_node["position"]["x"] + _pl_anchor_x_offset(idx, pl_node["properties"]["anchors"])

        checked = 0
        for c in result["connections"]:
            s, t = c["source"], c["target"]
            src_node = nodes_by_id.get(s["node"])
            if t["anchor"] == "PR" and src_node is not None and src_node["type"] == "PressureLine":
                ax = anchor_x(src_node, s["anchor"])
                tx = nodes_by_id[t["node"]]["position"]["x"]
                assert ax > tx, f"{s} -> {t}: anchor x={ax} não ficou à direita do alvo x={tx}"
                checked += 1
        assert checked > 0  # sanity check -- o cenário precisa exercitar pelo menos 1 conexão PR


class TestValvePilotEntryDoesNotJump:
    def test_v42_pl_pr_connections_enter_without_a_large_final_jump(self):
        # Regressão: circuit_generator.astar_router.SPRITE_SIZES tinha a
        # largura de Valve_4_2_Ways hardcoded em 447px, mas o sprite real
        # (sprite_metrics.py, lido do PNG) tem 300px -- 147px de diferença.
        # O retângulo de bloqueio de colisão do A* ficava 147px mais largo
        # que a válvula de verdade, e o anchor PR (que sprite_metrics.py
        # posiciona corretamente logo além da borda REAL do sprite) caía
        # "dentro" desse bloqueio inflado. O roteador escapava bem mais pra
        # longe do que precisava e desenhava um salto final enorme na
        # horizontal pra alcançar o anchor de volta -- o fio parecia entrar
        # pelo lado errado. Reproduzido com parse("A+A-B+B-").
        from circuit_generator.sprite_metrics import METRICS as _M

        data = step_by_step_pneumatic.generate(parse("A+A-B+B-"))
        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}
        node_type_map = {n["id"]: n["type"] for n in result["nodes"]}

        def anchor_x(node_id, anchor_name):
            node = node_by_id[node_id]
            ntype = node_type_map[node_id]
            pos = node["position"]
            if ntype == "PressureLine" and anchor_name.startswith("X"):
                idx = int(anchor_name[1:])
                return pos["x"] + _pl_anchor_x_offset(idx, node["properties"]["anchors"])
            local = _M.anchor_local.get(ntype, {}).get(anchor_name)
            return pos["x"] + local[0] if local else pos["x"]

        checked = 0
        for c in result["connections"]:
            t = c["target"]
            if t["anchor"] in ("PL", "PR") and node_type_map.get(t["node"]) == "Valve_4_2_Ways":
                wps = c.get("waypoints")
                if not wps:
                    continue  # linha reta -- sem salto possível
                last_x = wps[-1]["x"]
                tx = anchor_x(t["node"], t["anchor"])
                assert abs(last_x - tx) < 50, (
                    f"{c['source']} -> {t}: aproximação final salta "
                    f"{abs(last_x - tx):.1f}px na horizontal (last_x={last_x}, alvo_x={tx})"
                )
                checked += 1
        assert checked > 0  # sanity check -- o cenário precisa exercitar pelo menos 1 pilot PL/PR


class TestPilotAnchorRobustToCommutation:
    def test_last_memory_pr_anchor_clears_the_commutation_margin(self):
        # Regressão: gen-mc-3 (memória do último átomo) é a ÚNICA memória
        # com default_side="left" em "A+A-B+B-" -- sua posição REAL de
        # tela (com o deslocamento de comutação) fica 147px mais à
        # direita do que a fórmula base previa. O anchor de PressureLine
        # escolhido pelo layout precisa respeitar a posição REAL.
        from circuit_generator.sprite_metrics import anchor_local_for_routing, METRICS as _M

        data = step_by_step_pneumatic.generate(parse("A+A-B+B-"))
        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}

        mc3 = node_by_id["gen-mc-3"]
        assert mc3["properties"]["default_side"] == "left"  # sanity check do cenário

        worst_case_local = anchor_local_for_routing("Valve_3_2_Ways", "PR")
        worst_case_x = mc3["position"]["x"] + worst_case_local[0]

        conn = next(c for c in result["connections"]
                    if c["target"]["node"] == "gen-mc-3" and c["target"]["anchor"] == "PR")
        pl = node_by_id[conn["source"]["node"]]
        idx = int(conn["source"]["anchor"][1:])
        anchor_x = pl["position"]["x"] + _pl_anchor_x_offset(idx, pl["properties"]["anchors"])

        assert anchor_x > worst_case_x, (
            f"anchor x={anchor_x} não ficou à direita do pior caso "
            f"(com margem de comutação) x={worst_case_x}"
        )


class TestComponentToPressureLineDoesNotCrossThrough:
    def test_wire_approaches_the_pl_from_the_same_side_as_its_source(self):
        # Regressão: quando o alvo de uma conexão é uma PressureLine,
        # astar_router.route_connection calculava o "exit point" (ponto
        # onde o A* termina, antes do hop final até o anchor real) do
        # lado ERRADO da linha -- oposto de onde a conexão vem. O fio
        # cruzava a PressureLine inteira e voltava, um pequeno "vai-e-volta"
        # visível bem no ponto de conexão. Causa: dois comentários
        # contraditórios no código sobre o que tgt_dir_used="UP"/"DOWN"
        # significa quando a origem está abaixo/acima da PL -- o bloco que
        # calcula o exit point usava a convenção OPOSTA da que o bloco
        # anterior (que define tgt_dir_used) realmente usa.
        # Reproduzido com parse("A+A-B+B-"): gen-mc-0.A -> gen-pl-step0.X5
        # (origem abaixo da PL -- o exit point deveria ficar abaixo dela
        # também, nunca acima).
        data = step_by_step_pneumatic.generate(parse("A+A-B+B-"))
        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}
        node_type_map = {n["id"]: n["type"] for n in result["nodes"]}

        checked = 0
        for c in result["connections"]:
            s, t = c["source"], c["target"]
            if node_type_map.get(t["node"]) != "PressureLine":
                continue
            wps = c.get("waypoints")
            if not wps:
                continue
            src_y = node_by_id[s["node"]]["position"]["y"]
            pl_y = node_by_id[t["node"]]["position"]["y"]
            last_y = wps[-1]["y"]
            if src_y > pl_y:
                assert last_y >= pl_y, (
                    f"{s} -> {t}: origem está ABAIXO da PL (src_y={src_y} > "
                    f"pl_y={pl_y}), mas o último waypoint fica ACIMA dela "
                    f"(last_y={last_y}) -- o fio atravessa a PL e volta"
                )
            elif src_y < pl_y:
                assert last_y <= pl_y, (
                    f"{s} -> {t}: origem está ACIMA da PL (src_y={src_y} < "
                    f"pl_y={pl_y}), mas o último waypoint fica ABAIXO dela "
                    f"(last_y={last_y}) -- o fio atravessa a PL e volta"
                )
            checked += 1
        assert checked > 0  # sanity check -- o cenário precisa exercitar pelo menos 1 conexão pra PL


class TestPressureLineAnchorYAccountsForSpriteHeight:
    def test_routing_uses_the_real_rendered_anchor_y_not_just_node_position_y(self):
        # Regressão: graphics/items/base/nodes/expandable/pressure_line.py
        # posiciona os anchors da PressureLine em y0=self.pix_h -- ou
        # seja, pl_pix_h abaixo da posição do próprio nó. O roteamento
        # (via _scene_xy em step_by_step_layout.py) usava só pos["y"],
        # sem somar esse offset -- achava que o anchor estava pl_pix_h
        # mais ACIMA do que ele realmente é renderizado. Isso fazia
        # conexões que saem de uma PressureLine cruzarem de volta por
        # cima (ou por baixo, se o alvo estiver acima) da posição REAL
        # do anchor antes de seguir pro destino -- checa nos dois
        # sentidos, usando a posição (aproximada) do alvo pra saber qual
        # lado é o correto. Reproduzido com parse("A+A-B+B-"):
        # gen-pl-step0.X110 -> gen-mc-3.PR (o reset em anel do último
        # átomo, cuja fonte é a linha do PRIMEIRO átomo).
        from circuit_generator.sprite_metrics import METRICS as _M

        data = step_by_step_pneumatic.generate(parse("A+A-B+B-"))
        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}
        node_type_map = {n["id"]: n["type"] for n in result["nodes"]}

        checked = 0
        for c in result["connections"]:
            s, t = c["source"], c["target"]
            if node_type_map.get(s["node"]) != "PressureLine":
                continue
            wps = c.get("waypoints")
            if not wps:
                continue
            pl = node_by_id[s["node"]]
            real_pl_y = pl["position"]["y"] + _M.pl_pix_h
            target_y = node_by_id[t["node"]]["position"]["y"]
            for wp in wps:
                if target_y > real_pl_y:
                    assert wp["y"] >= real_pl_y - 1, (
                        f"{s} -> {t}: alvo está ABAIXO da PL, mas waypoint "
                        f"y={wp['y']} cruza de volta pra cima do anchor REAL "
                        f"da PL (y={real_pl_y})"
                    )
                elif target_y < real_pl_y:
                    assert wp["y"] <= real_pl_y + 1, (
                        f"{s} -> {t}: alvo está ACIMA da PL, mas waypoint "
                        f"y={wp['y']} cruza de volta pra baixo do anchor REAL "
                        f"da PL (y={real_pl_y})"
                    )
            checked += 1
        assert checked > 0  # sanity check -- o cenário precisa exercitar pelo menos 1 conexão saindo de uma PL


class TestPressureLineToSigPAnchorClearsTheValve:
    def test_anchor_is_left_of_the_valve_body_and_limit_switch(self):
        # Regressão: o anchor de PressureLine escolhido pra uma conexão
        # PL -> Valve_3_2_Ways.P (cadeia de confirmação) era sempre o
        # "mais próximo" da válvula, sem levar em conta que o fio desce
        # reto a partir desse anchor -- se a válvula (e outras no mesmo
        # eixo X, como MC_0/botão na coluna de fechamento) estiverem bem
        # abaixo, o traço passa por DENTRO delas. O anchor precisa ficar
        # à esquerda do corpo da válvula E do atuador de fim-de-curso
        # (limit_switch, mesma largura do pilot: METRICS.pilot_w).
        # Reproduzido com parse("A+B+A-B-"):
        # gen-pl-step3.X* -> gen-sig-B-ret-3.P.
        from circuit_generator.sprite_metrics import METRICS as _M

        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}
        node_type_map = {n["id"]: n["type"] for n in result["nodes"]}

        checked = 0
        for c in result["connections"]:
            s, t = c["source"], c["target"]
            if t["anchor"] != "P" or node_type_map.get(t["node"]) != "Valve_3_2_Ways":
                continue
            if node_type_map.get(s["node"]) != "PressureLine":
                continue
            pl = node_by_id[s["node"]]
            idx = int(s["anchor"][1:])
            anchor_x = pl["position"]["x"] + _pl_anchor_x_offset(idx, pl["properties"]["anchors"])
            valve_left_x = node_by_id[t["node"]]["position"]["x"]
            safe_x = valve_left_x - _M.pilot_w
            assert anchor_x <= safe_x, (
                f"{s} -> {t}: anchor x={anchor_x} não ficou à esquerda da "
                f"válvula+fim-de-curso (limite seguro x={safe_x})"
            )
            checked += 1
        assert checked > 0  # sanity check -- o cenário precisa exercitar pelo menos 1 conexão PL->sig.P

    def test_wire_routes_around_other_valves_instead_of_through_them(self):
        # Mesma regressão do teste acima, mas verificando o efeito real:
        # nenhum segmento do fio atravessa o retângulo de OUTRA válvula
        # no meio do caminho.
        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}
        node_type_map = {n["id"]: n["type"] for n in result["nodes"]}

        obstacle_types = {"Valve_3_2_Ways", "Valve_4_2_Ways", "Valve_5_2_Ways", "DoubleActingCylinder"}
        checked = 0
        for c in result["connections"]:
            s, t = c["source"], c["target"]
            if t["anchor"] != "P" or node_type_map.get(s["node"]) != "PressureLine":
                continue
            wps = c.get("waypoints")
            if not wps:
                continue
            pts = ([_anchor_xy(node_by_id, s["node"], s["anchor"])]
                   + [(wp["x"], wp["y"]) for wp in wps]
                   + [_anchor_xy(node_by_id, t["node"], t["anchor"])])
            for other_id, other in node_by_id.items():
                if other_id in (s["node"], t["node"]):
                    continue
                if node_type_map.get(other_id) not in obstacle_types:
                    continue
                r = _obstacle_rect(node_by_id, other_id)
                for a, b in zip(pts, pts[1:]):
                    assert not _seg_crosses_rect(a, b, r), (
                        f"{s} -> {t}: segmento {a}->{b} atravessa {other_id} "
                        f"(retângulo {r}) em vez de desviar"
                    )
            checked += 1
        assert checked > 0  # sanity check -- o cenário precisa exercitar pelo menos 1 conexão PL->sig.P


class TestOrValvePlacement:
    def test_or_valve_chain_sits_on_its_own_row_below_main_valve(self):
        # A cadeia de OrValve fica um pouco ABAIXO da 4/2 (não entre
        # cilindro e 4/2) -- ver docs/superpowers/specs/
        # 2026-07-12-step-by-step-multi-cycle-or-valve-design.md.
        import json
        cfg = json.loads(layout._CONFIG_PATH.read_text(encoding="utf-8"))
        mv_y = cfg["rows"]["main_valve"]

        data = step_by_step_pneumatic.generate(parse("A+B+A-A+B-A-"))
        result = layout.apply(data)
        or_nodes = [n for n in result["nodes"] if n["type"] == "OrValve"]
        assert len(or_nodes) == 2
        for n in or_nodes:
            assert n["position"] != {"x": 0, "y": 0}
            assert n["position"]["y"] > mv_y
        # todas as OrValve do circuito ficam na MESMA linha (crescem só em X)
        assert len({n["position"]["y"] for n in or_nodes}) == 1

    def test_or_valve_chain_grows_to_the_correct_side_of_its_cylinder(self):
        # PL (lado "+") cresce à ESQUERDA do cilindro; PR (lado "-") à DIREITA.
        #
        # role_by_id é capturado ANTES de layout.apply(data): apply() muta
        # data in-place e remove "_role" de todo nó no fim (ver "Limpeza
        # final" em step_by_step_layout.py, e o invariante já coberto por
        # test_every_node_has_role_removed) -- ler n["_role"] em result
        # depois do apply() sempre daria KeyError, então a identificação
        # por role precisa vir de um snapshot tirado antes da chamada.
        data = step_by_step_pneumatic.generate(parse("A+B+A-A+B-A-"))
        role_by_id = {n["id"]: n.get("_role", "") for n in data["nodes"]}
        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}
        cyl_a_x = node_by_id["gen-cyl-A"]["position"]["x"]

        pl_or_id = next(nid for nid, role in role_by_id.items() if role == "or_valve:A:PL:0")
        pr_or_id = next(nid for nid, role in role_by_id.items() if role == "or_valve:A:PR:0")
        assert node_by_id[pl_or_id]["position"]["x"] < cyl_a_x
        assert node_by_id[pr_or_id]["position"]["x"] > cyl_a_x

    def test_or_valve_chain_of_two_does_not_overlap_itself(self):
        import json
        cfg = json.loads(layout._CONFIG_PATH.read_text(encoding="utf-8"))
        group_gap = cfg["columns"]["group_gap"]

        # role_by_id: mesmo motivo do teste acima (snapshot antes do apply()).
        data = step_by_step_pneumatic.generate(parse("A+A-A+A-A+A-"))
        role_by_id = {n["id"]: n.get("_role", "") for n in data["nodes"]}
        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}
        pl_or_ids = sorted(
            (nid for nid, role in role_by_id.items() if role.startswith("or_valve:A:PL:")),
            key=lambda nid: role_by_id[nid],
        )
        assert len(pl_or_ids) == 2
        xs = sorted(node_by_id[nid]["position"]["x"] for nid in pl_or_ids)
        assert xs[1] - xs[0] == group_gap


class TestMultiCycleEndToEnd:
    def test_no_node_left_at_origin_for_multi_cycle_sequence(self):
        data = step_by_step_pneumatic.generate(parse("A+B+A-A+B-A-"))
        result = layout.apply(data)
        at_origin = [n["id"] for n in result["nodes"]
                     if n["position"]["x"] == 0 and n["position"]["y"] == 0]
        assert at_origin == []

    def test_or_valve_does_not_cross_any_valve_or_cylinder(self):
        # Mesmo estilo geométrico já usado pra PL -> Valve_3_2_Ways.P
        # (ver TestPressureLineToSigPAnchorClearsTheValve): nenhum
        # segmento de fio que toca uma OrValve atravessa o retângulo de
        # OUTRO componente.
        data = step_by_step_pneumatic.generate(parse("A+B+A-A+B-A-"))
        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}
        node_type_map = {n["id"]: n["type"] for n in result["nodes"]}

        obstacle_types = {"Valve_3_2_Ways", "Valve_4_2_Ways", "Valve_5_2_Ways",
                           "DoubleActingCylinder", "OrValve"}
        checked = 0
        for c in result["connections"]:
            s, t = c["source"], c["target"]
            if node_type_map.get(s["node"]) != "OrValve" and node_type_map.get(t["node"]) != "OrValve":
                continue
            wps = c.get("waypoints")
            if not wps:
                continue
            pts = ([_anchor_xy(node_by_id, s["node"], s["anchor"])]
                   + [(wp["x"], wp["y"]) for wp in wps]
                   + [_anchor_xy(node_by_id, t["node"], t["anchor"])])
            for other_id, other in node_by_id.items():
                if other_id in (s["node"], t["node"]):
                    continue
                if node_type_map.get(other_id) not in obstacle_types:
                    continue
                r = _obstacle_rect(node_by_id, other_id)
                for i in range(len(pts) - 1):
                    assert not _seg_crosses_rect(pts[i], pts[i + 1], r), (
                        f"{s} -> {t} crosses {other_id} ({node_type_map[other_id]})"
                    )
            checked += 1
        assert checked > 0


class TestSigChainPAnchorRouting:
    def test_stacked_sig_chain_routes_as_a_straight_vertical_line(self):
        """Reprodução exata do bug reportado pelo usuário: duas válvulas
        de sinalização empilhadas na MESMA coluna (bloco paralelo
        C+(A+B+)C-A-B-) conectadas por um elo A->P devem rotear com uma
        linha reta vertical -- sem desvio pro offset de comutação errado
        (ver docs/superpowers/specs/2026-08-12-sig-chain-p-anchor-offset-design.md)."""
        data = step_by_step_pneumatic.generate(parse("C+(A+B+)C-A-B-"))
        result = layout.apply(data)

        sig_a = _node(result, "gen-sig-A-ext-1")
        sig_b = _node(result, "gen-sig-B-ext-2")
        assert sig_a["position"]["x"] == sig_b["position"]["x"], (
            "fixture não está mais empilhada na mesma coluna -- ajuste o teste"
        )

        conn = next(
            c for c in result["connections"]
            if c["source"]["node"] == "gen-sig-A-ext-1" and c["target"]["node"] == "gen-sig-B-ext-2"
        )
        wps = conn.get("waypoints") or []
        # Todo waypoint (se houver) deve ficar na mesma coluna X do anchor A
        # (roteamento reto) -- nenhum desvio de 147px pro offset errado.
        from circuit_generator.sprite_metrics import anchor_local_for_routing
        expected_x = sig_a["position"]["x"] + anchor_local_for_routing("Valve_3_2_Ways", "A")[0]
        assert wps == [], f"esperava rota reta sem waypoints, achou {wps}"
        for wp in wps:
            assert abs(wp["x"] - expected_x) < 1.0, (
                f"waypoint {wp} desviou da coluna reta esperada (x={expected_x}) -- "
                f"offset de comutação sendo aplicado indevidamente?"
            )
