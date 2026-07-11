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
