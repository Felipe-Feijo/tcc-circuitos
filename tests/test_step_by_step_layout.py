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
