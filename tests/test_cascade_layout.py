import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.sequence_parser import parse
from circuit_generator.methods import cascade
from circuit_generator import cascade_layout as layout


def _node(data, node_id):
    return next(n for n in data["nodes"] if n["id"] == node_id)


class TestRoleMaps:
    def test_role_maps_extract_cylinders_v42_pl_memory(self):
        # NOTE: the brief's literal draft used "A+B+A-B-A+A-" here, but that
        # sequence produces 4 pressure_line_group nodes and 3 memory nodes
        # under cascade.generate()'s (unchanged) grouping algorithm --
        # verified via sequence_parser.split_into_groups, which starts a new
        # cascade group whenever a letter repeats within the current group:
        # "A+B+A-B-A+A-" -> [[A+,B+],[A-,B-],[A+],[A-]] (4 groups), not the
        # 2 groups / 1 memory this test asserts. "A+B+A-B-" (this sequence,
        # without the trailing "A+A-") is the shortest input that actually
        # produces the asserted role maps -- confirmed by running
        # cascade.generate() directly.
        data = cascade.generate(parse("A+B+A-B-"))
        roles = layout._build_role_maps(data)
        assert roles["cyl_by_letter"] == {"A": "gen-cyl-A", "B": "gen-cyl-B"}
        assert roles["v42_by_letter"] == {"A": "gen-v42-A", "B": "gen-v42-B"}
        assert roles["pl_by_idx"] == {0: "gen-pl-grp1", 1: "gen-pl-grp2"}
        assert roles["mc_by_idx"] == {0: "gen-mc-0"}
        assert roles["btn_id"] == "gen-btn"
        assert roles["n_groups"] == 2
        assert roles["n_mc"] == 1


class TestPistonValveRegion:
    def test_cylinders_and_v42_positioned_same_column_per_letter(self):
        data = cascade.generate(parse("A+B+A-B-A+A-"))
        result = layout.apply(data)
        cyl_a = _node(result, "gen-cyl-A")
        v42_a = _node(result, "gen-v42-A")
        assert cyl_a["position"]["x"] == v42_a["position"]["x"]
        assert cyl_a["position"]["y"] != v42_a["position"]["y"]

    def test_different_letters_get_different_columns(self):
        data = cascade.generate(parse("A+B+A-B-A+A-"))
        result = layout.apply(data)
        cyl_a = _node(result, "gen-cyl-A")
        cyl_b = _node(result, "gen-cyl-B")
        assert cyl_a["position"]["x"] != cyl_b["position"]["x"]


class TestTriggerSourceChains:
    def test_single_group_no_repeat_gives_one_raw_leaf_per_side(self):
        # "A+B+A-B-": split_into_groups gives 2 groups ([A+,B+], [A-,B-]),
        # each atomized into 2 single-event atoms (no parallel blocks, so
        # every event is its own atom -- see cascade._atomize_group). Only
        # the FIRST atom of a group is a raw source (entry_sources is None
        # -> fed straight from the group's PressureLine bus); every later
        # atom in the same group is triggered by the confirmation sig of
        # the atom before it. A+ is the first atom of group 0 -> raw.
        # B+ is the SECOND atom of group 0 -> NOT raw, it is confirmed by
        # a single sig (the "A extended" limit switch), depth 1.
        #
        # The brief's literal draft asserted sources[("B", "PR")] == [[]]
        # (claiming "every source here is the first atom of its group, so
        # every source is raw"), but B- is the second atom of group 1
        # (after A-), just like B+ is the second atom of group 0 -- so
        # its PR side is fed by 1 sig (gen-sig-A-ret-2, confirming A-),
        # not raw. Verified by dumping cascade.generate(parse("A+B+A-B-"))
        # ["connections"] directly: it contains
        # "gen-sig-A-ret-2.A -> gen-v42-B.PR" (a sig->pilot edge), and
        # "gen-pl-grp2.X3 -> gen-sig-A-ret-2.P" (that sig's P comes
        # straight from the group bus, i.e. depth 1, not chained further).
        data = cascade.generate(parse("A+B+A-B-"))
        roles = layout._build_role_maps(data)
        sources = layout._build_trigger_sources(data, roles)
        assert sources[("A", "PL")] == [[]]
        assert sources[("B", "PR")] == [["gen-sig-A-ret-2"]]

    def test_repeated_movement_gives_two_leaves(self):
        # "A+B+A-B-B+B-": B+ ocorre 2x (grupo1 átomo1, grupo2 átomo0) ->
        # 2 fontes no lado PL de B. A segunda ocorrência (grupo2, primeiro
        # átomo do grupo) é crua; a primeira (grupo1, NÃO primeiro átomo,
        # precedida por A+) vem de 1 sig (confirmação de A+, fan_out=1).
        data = cascade.generate(parse("A+B+A-B-B+B-"))
        roles = layout._build_role_maps(data)
        sources = layout._build_trigger_sources(data, roles)
        leaves = sources[("B", "PL")]
        assert len(leaves) == 2
        depths = sorted(len(leaf) for leaf in leaves)
        assert depths == [0, 1]

    def test_leaf_preceded_by_parallel_block_has_depth_two(self):
        # "(A+C+)B+A-B-C-B+B-": B+ ocorre 2x. A 1a ocorrência (grupo1,
        # átomo1) é precedida pelo bloco (A+C+) (átomo0, 2 eventos) ->
        # cadeia serial de 2 sigs. A 2a ocorrência (grupo2, átomo0) é
        # crua.
        data = cascade.generate(parse("(A+C+)B+A-B-C-B+B-"))
        roles = layout._build_role_maps(data)
        sources = layout._build_trigger_sources(data, roles)
        leaves = sources[("B", "PL")]
        assert len(leaves) == 2
        depths = sorted(len(leaf) for leaf in leaves)
        assert depths == [0, 2]


class TestOrSigStaircase:
    def test_multi_cycle_creates_one_or_and_two_leaf_columns(self):
        # "A+B+A-B-B+B-": B+ tem 2 fontes -> 1 OrValve, 2 colunas de folha.
        data = cascade.generate(parse("A+B+A-B-B+B-"))
        result = layout.apply(data)
        or_nodes = [n for n in result["nodes"] if n["type"] == "OrValve"]
        assert len(or_nodes) == 2  # 1 no lado PL de B, 1 no lado PR de B
        for n in or_nodes:
            assert n["position"] != {"x": 0, "y": 0}
        # 2 colunas distintas por lado -> 2 x distintos entre as 2 OrValve
        xs = {round(n["position"]["x"]) for n in or_nodes}
        assert len(xs) == 2

    def test_deep_leaf_chain_stacks_vertically_without_colliding(self):
        # "(A+C+)B+A-B-C-B+B-": uma das folhas de B+ tem cadeia de
        # profundidade 2 -- as 2 sigs dessa cadeia ficam na MESMA coluna,
        # linhas diferentes.
        data = cascade.generate(parse("(A+C+)B+A-B-C-B+B-"))
        roles = layout._build_role_maps(data)
        sources = layout._build_trigger_sources(data, roles)
        deep_leaf = next(leaf for leaf in sources[("B", "PL")] if len(leaf) == 2)
        result = layout.apply(data)
        sig0 = _node(result, deep_leaf[0])
        sig1 = _node(result, deep_leaf[1])
        assert sig0["position"]["x"] == sig1["position"]["x"]
        assert sig0["position"]["y"] != sig1["position"]["y"]

    def test_pl_and_pr_or_rows_align_at_the_same_height_per_cylinder(self):
        # A altura (linhas) da região de OR/sig é uniforme pros dois lados
        # do MESMO cilindro -- mesmo se só um lado tiver cadeia profunda.
        data = cascade.generate(parse("(A+C+)B+A-B-C-B+B-"))
        role_by_id = {n["id"]: n.get("_role", "") for n in data["nodes"]}
        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}
        pl_or = next(nid for nid, r in role_by_id.items() if r.startswith("or_valve:B:PL:"))
        pr_or = next(nid for nid, r in role_by_id.items() if r.startswith("or_valve:B:PR:"))
        assert node_by_id[pl_or]["position"]["y"] == node_by_id[pr_or]["position"]["y"]

    def test_or_rows_are_shared_globally_across_different_cylinders(self):
        # Documenta explicitamente o design ATUAL (intencional, não
        # acidental): or_row e sig_stack_{depth} são linhas GLOBAIS,
        # compartilhadas por TODOS os cilindros do circuito -- não uma
        # linha por cilindro. Isso é uma consequência mais forte do que
        # "PL e PR do MESMO cilindro compartilham altura" (que também vale,
        # ver test_pl_and_pr_or_rows_align_at_the_same_height_per_cylinder),
        # mas é o comportamento real hoje: aqui, tanto o OR de B (lado PL)
        # quanto o OR de C (lado PL) caem na mesma or_row -> mesmo y.
        data = cascade.generate(parse("A+B+C+A-B-C-A+B+C+A-B-C-"))
        role_by_id = {n["id"]: n.get("_role", "") for n in data["nodes"]}
        result = layout.apply(data)
        node_by_id = {n["id"]: n for n in result["nodes"]}
        b_or = next(nid for nid, r in role_by_id.items() if r.startswith("or_valve:B:PL:"))
        c_or = next(nid for nid, r in role_by_id.items() if r.startswith("or_valve:C:PL:"))
        assert node_by_id[b_or]["position"]["y"] == node_by_id[c_or]["position"]["y"]
        assert node_by_id[b_or]["position"]["x"] != node_by_id[c_or]["position"]["x"]

    def test_multi_cylinder_multi_cycle_sequence_does_not_raise_and_has_no_collisions(self):
        # Regressão: sequência com 3 cilindros e 2 ciclos completos produz,
        # pro lado PR de cada cilindro, folhas cujo vcol é DESCENDENTE em j
        # (offset = n pra j==0, depois n-j) -- chamar _place_aligned na
        # ordem de iteração de j (em vez de ordem ascendente de vcol)
        # colidia com um placeholder já reservado e lançava ValueError.
        # Ver circuit_generator/cascade_layout.py, bloco "Posiciona as
        # cadeias de sig de cada folha".
        # Nem todo Valve_3_2_Ways gerado entra numa cadeia de folha desta
        # Região A (alguns sigs só serão usados na Região B, Tasks 4/5,
        # ainda não implementada) -- esses ficam no placeholder {0, 0} de
        # cascade.generate e são ignorados aqui, mesma convenção já usada
        # em test_multi_cycle_creates_one_or_and_two_leaf_columns acima.
        data = cascade.generate(parse("A+B+C+A-B-C-A+B+C+A-B-C-"))
        result = layout.apply(data)  # não deve lançar ValueError
        positions = [(n["position"]["x"], n["position"]["y"]) for n in result["nodes"]
                     if n["type"] in ("Valve_3_2_Ways", "OrValve")
                     and n["position"] != {"x": 0, "y": 0}]
        assert len(positions) == len(set(positions))


class TestLogicRegionRows:
    # NOTE: the brief's literal draft used "A+B+A-B-A+A-" for every test in
    # this class, with a "# n_groups=2, n_mc=1" comment. As already found in
    # TestRoleMaps above, that sequence actually produces n_groups=4,
    # n_mc=3 under cascade.generate()'s grouping algorithm -- confirmed by
    # running layout._build_role_maps() directly. With n_groups=4, mem[0].B
    # connects to pl_grp[M-1-0] = pl_grp4 (0-idx 3), not pl_grp2 (0-idx 1)
    # as test_memory_sits_on_the_row_of_the_pl_it_drives_via_b asserts --
    # confirmed by dumping cascade.generate(parse("A+B+A-B-A+A-"))
    # ["connections"]: it contains "gen-mc-0 B -> gen-pl-grp4 X1", never
    # "-> gen-pl-grp2". "A+B+A-B-" (used by TestRoleMaps for the same
    # reason) is the shortest sequence that actually yields the n_groups=2,
    # n_mc=1 the brief's comment and assertions assume -- verified the same
    # way: it produces "gen-mc-0 B -> gen-pl-grp2 X1", matching the test.
    def test_pressure_lines_are_grid_rows_stacked_by_group_index(self):
        data = cascade.generate(parse("A+B+A-B-"))  # n_groups=2, n_mc=1
        result = layout.apply(data)
        pl0 = _node(result, "gen-pl-grp1")
        pl1 = _node(result, "gen-pl-grp2")
        assert pl0["position"]["y"] < pl1["position"]["y"]
        assert pl0["position"] != {"x": 0, "y": 0}

    def test_memory_sits_on_the_row_of_the_pl_it_drives_via_b(self):
        # mem[0].B -> pl_grp[n_groups-1] (a última) -- mem[0] fica na
        # mesma linha local M (a mais baixa) que pl_grp[1] (0-indexado).
        data = cascade.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        mc0 = _node(result, "gen-mc-0")
        pl1 = _node(result, "gen-pl-grp2")
        assert mc0["position"]["y"] == pl1["position"]["y"]

    def test_button_sits_one_row_below_the_bottom_memory(self):
        import json
        cfg = json.loads(layout._CONFIG_PATH.read_text(encoding="utf-8"))
        row_gap = cfg["rows"]["logic_row_gap"]

        data = cascade.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        mc0 = _node(result, "gen-mc-0")
        btn = _node(result, "gen-btn")
        assert btn["position"]["y"] == mc0["position"]["y"] + row_gap
        assert btn["position"]["x"] != mc0["position"]["x"]

    def test_memories_and_button_occupy_distinct_columns(self):
        data = cascade.generate(parse("A+B+A-B-"))
        result = layout.apply(data)
        mc0 = _node(result, "gen-mc-0")
        btn = _node(result, "gen-btn")
        assert mc0["position"]["x"] != btn["position"]["x"]


class TestConfirmationStaircase:
    def test_no_two_confirmation_sigs_share_a_column_across_rows(self):
        # 5 groups, 4 memories under cascade.generate()'s grouping (verified
        # via layout._build_role_maps -- the brief's draft comment said
        # "3 groups, 2 memories", which is not what this sequence produces).
        data = cascade.generate(parse("A+B+A-B-A+A-C+C-"))
        result = layout.apply(data)
        role_by_id = {n["id"]: n.get("_role", "") for n in
                      cascade.generate(parse("A+B+A-B-A+A-C+C-"))["nodes"]}
        confirm_sigs = [n for n in result["nodes"]
                        if n["type"] == "Valve_3_2_Ways"
                        and role_by_id.get(n["id"], "").startswith("signal_valve:")
                        and n["position"]["x"] > _node(result, "gen-mc-0")["position"]["x"]]
        xs = [round(n["position"]["x"]) for n in confirm_sigs]
        assert len(xs) == len(set(xs)), f"colunas repetidas: {xs}"

    def test_topmost_memory_confirmation_is_the_innermost_column(self):
        # NOTE: the brief's draft used a guessed id "gen-sig-C-ret-9" here.
        # Verified the real id by running cascade.generate(parse(...)) and
        # dumping data["connections"] for the (letter, "PR") edges into each
        # mem[i].PR: with n_mc=4, mc_by_idx = {0: gen-mc-0, .., 3: gen-mc-3},
        # and the topmost row (offset 0, processed first by apply()'s
        # ordered_targets = mc_by_idx[n_mc-1 .. 0]) is gen-mc-3 (smallest y
        # -- confirmed both by pl_row_y/local-row arithmetic in Task 4's
        # code and by directly reading positions after layout.apply()).
        # gen-mc-3.PR is fed straight from a PressureLine via a single sig,
        # gen-sig-B-ext-1 (connection "gen-sig-B-ext-1.A -> gen-mc-3.PR",
        # "gen-pl-grp1.X4 -> gen-sig-B-ext-1.P") -- chain length 1, so it
        # lands at offset 0 -> virtual_col 1 -> mem_col_x + one cell width.
        data = cascade.generate(parse("A+B+A-B-A+A-C+C-"))
        result = layout.apply(data)
        mem_col_x = _node(result, "gen-mc-1")["position"]["x"]  # any mem: shared column
        confirm = _node(result, "gen-sig-B-ext-1")
        assert confirm["position"]["x"] == mem_col_x + layout._logic_cell_width()

    def test_deep_row_confirmation_grows_in_columns_not_rows(self):
        # Se a confirmação de uma memória for uma cadeia de 2 sigs (bloco
        # paralelo antes dela), as 2 sigs ficam na MESMA linha (mesmo y),
        # colunas diferentes.
        #
        # NOTE: the brief's draft filtered on
        # role.startswith("signal_valve:2") assuming role encodes chain
        # depth -- it does not (cascade.py builds it as
        # f"signal_valve:{g_idx*100+e_idx}{role_suffix}", verified by
        # reading circuit_generator/methods/cascade.py line ~299 and by
        # dumping the real roles for this sequence: no role starts with
        # "signal_valve:2" at all here). Verified directly instead, by
        # walking the mem[i].PR chains the same way apply() does: for
        # "A+B+(A-B-)A+A-" (n_groups=4, n_mc=3), mem[1] (gen-mc-1) is the
        # only target whose confirmation chain has length 2 --
        # ["gen-sig-A-ret-2", "gen-sig-B-ret-3"] (the parallel block
        # (A-B-) preceding it).
        data = cascade.generate(parse("A+B+(A-B-)A+A-"))
        result = layout.apply(data)
        chain_sigs = [_node(result, "gen-sig-A-ret-2"), _node(result, "gen-sig-B-ret-3")]
        assert chain_sigs[0]["position"]["y"] == chain_sigs[1]["position"]["y"]
        assert chain_sigs[0]["position"]["x"] != chain_sigs[1]["position"]["x"]
