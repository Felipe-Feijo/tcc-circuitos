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
    def test_mc0_button_closure_sig_share_same_column(self):
        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        mc0 = _node(result, "gen-mc-0")
        btn = _node(result, "gen-btn")
        closure_sig = _node(result, "gen-sig-B-ret-3")
        assert mc0["position"]["x"] == btn["position"]["x"] == closure_sig["position"]["x"]
        assert mc0["position"]["y"] < btn["position"]["y"] < closure_sig["position"]["y"]

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
        # último átomo é um bloco paralelo -- fechamento tem 2 sigs em série
        data = step_by_step_pneumatic.generate(parse("A+B+(A-B-)"))
        result = layout.apply(data)
        mc0 = _node(result, "gen-mc-0")
        btn = _node(result, "gen-btn")
        sig0 = _node(result, "gen-sig-A-ret-2")
        sig1 = _node(result, "gen-sig-B-ret-3")

        assert sig0["position"] != {"x": 0, "y": 0}
        assert sig1["position"] != {"x": 0, "y": 0}
        assert mc0["position"]["x"] == btn["position"]["x"] == \
            sig0["position"]["x"] == sig1["position"]["x"]
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
        from circuit_generator.sprite_metrics import METRICS as _M

        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        pl_conns = [c for c in result["connections"]
                    if c["source"]["anchor"].startswith("X") or c["target"]["anchor"].startswith("X")]
        assert len(pl_conns) > 0

        nodes_by_id = {n["id"]: n for n in result["nodes"]}

        def _anchor_x(node_id: str, anchor: str) -> float:
            node = nodes_by_id[node_id]
            x = node["position"]["x"]
            if node["type"] == "PressureLine" and anchor.startswith("X"):
                idx = int(anchor[1:])
                return x + _M.pl_pix_w / 2 + (idx - 1) * _M.pl_spacing
            local = _M.anchor_local.get(node["type"], {}).get(anchor)
            return x + local[0] if local else x

        STRAIGHT_THRESHOLD_PX = 3  # mirrors astar_router.route_connection's shortcut

        needs_routing = []
        for c in pl_conns:
            sx = _anchor_x(c["source"]["node"], c["source"]["anchor"])
            tx = _anchor_x(c["target"]["node"], c["target"]["anchor"])
            if abs(sx - tx) >= STRAIGHT_THRESHOLD_PX:
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
        # ser o mais próximo (ou empatado) da posição X de gen-v42-A
        # entre TODOS os anchors da linha, não um arbitrário.
        data = step_by_step_pneumatic.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        pl0 = next(n for n in result["nodes"] if n["id"] == "gen-pl-step0")
        v42a = next(n for n in result["nodes"] if n["id"] == "gen-v42-A")
        conn = next(c for c in result["connections"]
                    if c["source"]["node"] == "gen-pl-step0" and c["target"]["node"] == "gen-v42-A"
                    and c["target"]["anchor"] == "PL")
        chosen_idx = int(conn["source"]["anchor"][1:])
        chosen_x = pl0["position"]["x"] + _pl_anchor_x_offset(chosen_idx)
        target_x = v42a["position"]["x"]
        # nenhum outro anchor da linha pode estar estritamente mais perto
        for a in pl0["properties"]["anchors"]:
            idx = int(a[1:])
            ax = pl0["position"]["x"] + _pl_anchor_x_offset(idx)
            assert abs(ax - target_x) >= abs(chosen_x - target_x) - 1e-6


def _pl_anchor_x_offset(idx):
    from circuit_generator.sprite_metrics import METRICS as _M
    return _M.pl_pix_w / 2 + (idx - 1) * _M.pl_spacing


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
        from circuit_generator.sprite_metrics import METRICS as _M

        letters = list(string.ascii_uppercase[:16])
        events = [(l, "+", "ext") for l in letters] + [(l, "-", "ret") for l in letters]
        data = step_by_step_pneumatic.generate(events)
        result = layout.apply(data)
        nodes_by_id = {n["id"]: n for n in result["nodes"]}

        def anchor_x(pl_node, anchor_name):
            idx = int(anchor_name[1:])
            return pl_node["position"]["x"] + _M.pl_pix_w / 2 + (idx - 1) * _M.pl_spacing

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
