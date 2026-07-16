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
