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
