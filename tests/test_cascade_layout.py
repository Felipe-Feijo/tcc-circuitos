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
