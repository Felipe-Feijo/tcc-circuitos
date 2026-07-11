"""Testes para circuit_generator/methods/step_by_step_pneumatic.py — ver
docs/superpowers/specs/2026-07-10-step-by-step-pneumatic-design.md
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.sequence_parser import parse
from circuit_generator.methods import step_by_step_pneumatic as sbs
from circuit_generator.methods.step_by_step_pneumatic import _atomize


def _conns_from(data, node_id, anchor=None):
    return [c for c in data["connections"]
            if c["source"]["node"] == node_id
            and (anchor is None or c["source"]["anchor"] == anchor)]


def _conns_to(data, node_id, anchor=None):
    return [c for c in data["connections"]
            if c["target"]["node"] == node_id
            and (anchor is None or c["target"]["anchor"] == anchor)]


class TestAtomize:
    def test_no_parallel_ids_each_event_is_its_own_atom(self):
        events = [("A", "+", None), ("B", "+", None)]
        assert _atomize(events) == [
            [(0, "A", "+")],
            [(1, "B", "+")],
        ]

    def test_two_tuples_without_parallel_id_field(self):
        events = [("A", "+"), ("B", "+")]
        assert _atomize(events) == [
            [(0, "A", "+")],
            [(1, "B", "+")],
        ]

    def test_single_block_is_one_atom(self):
        events = [("A", "+", 0), ("B", "+", 0)]
        assert _atomize(events) == [
            [(0, "A", "+"), (1, "B", "+")],
        ]

    def test_event_then_block(self):
        events = [("C", "+", None), ("A", "+", 0), ("B", "+", 0)]
        assert _atomize(events) == [
            [(0, "C", "+")],
            [(1, "A", "+"), (2, "B", "+")],
        ]

    def test_atomize_ignores_group_boundaries_unlike_cascade(self):
        # Ao contrário de cascade._atomize_group (que opera por grupo
        # cascata), _atomize aqui opera sobre a sequência inteira -- não
        # há corte por repetição de letra, só por parallel_id.
        events = [("A", "+", None), ("A", "-", None), ("B", "+", 0), ("C", "+", 0)]
        assert _atomize(events) == [
            [(0, "A", "+")],
            [(1, "A", "-")],
            [(2, "B", "+"), (3, "C", "+")],
        ]


class TestMultiCycleGuard:
    def test_repeated_letter_direction_pair_raises_not_implemented(self):
        # "A+B+A-A+B-A-": A+ aparece em dois átomos não-adjacentes --
        # multi-ciclo, fora de escopo (ver spec, seção "Fora de escopo").
        events = parse("A+B+A-A+B-A-")
        with pytest.raises(NotImplementedError):
            sbs.generate(events)

    def test_single_cycle_sequence_does_not_raise(self):
        events = parse("A+B+A-B-")
        sbs.generate(events)  # não deve levantar


class TestBoilerplate:
    """Cilindros, válvulas 4/2 e botão -- mesma estrutura usada pelo
    cascata, independente da divisão em átomos."""

    def test_cylinders_and_v42_created_for_each_letter(self):
        data = sbs.generate(parse("A+B+A-B-"))
        cyl_ids = {n["id"] for n in data["nodes"] if n["type"] == "DoubleActingCylinder"}
        v42_ids = {n["id"] for n in data["nodes"] if n["type"] == "Valve_4_2_Ways"}
        assert cyl_ids == {"gen-cyl-A", "gen-cyl-B"}
        assert v42_ids == {"gen-v42-A", "gen-v42-B"}

    def test_v42_connected_to_cylinder(self):
        data = sbs.generate(parse("A+B+A-B-"))
        assert _conns_to(data, "gen-cyl-A", "A")[0]["source"]["node"] == "gen-v42-A"
        assert _conns_to(data, "gen-cyl-A", "B")[0]["source"]["node"] == "gen-v42-A"

    def test_button_created_with_exhaust(self):
        data = sbs.generate(parse("A+B+A-B-"))
        btn = next(n for n in data["nodes"] if n["id"] == "gen-btn")
        assert btn["type"] == "Valve_3_2_Ways"
        assert btn["properties"]["actuators"]["left"]["type"] == "button"
        assert len(_conns_to(data, "gen-btn", "R")) == 1


class TestAtomLinesAndMemory:
    """Uma PressureLine + uma memória Valve_3_2_Ways biestável por átomo,
    nunca compartilhadas. Reset em anel; só o botão seta MC_0."""

    def test_one_pressure_line_and_memory_per_atom(self):
        data = sbs.generate(parse("A+B+A-B-"))  # 4 átomos de 1 evento
        pl_ids = {n["id"] for n in data["nodes"] if n["type"] == "PressureLine"}
        mc_ids = {n["id"] for n in data["nodes"]
                  if n["type"] == "Valve_3_2_Ways" and n["_role"].startswith("memory:")}
        assert pl_ids == {"gen-pl-step0", "gen-pl-step1", "gen-pl-step2", "gen-pl-step3"}
        assert mc_ids == {"gen-mc-0", "gen-mc-1", "gen-mc-2", "gen-mc-3"}

    def test_parallel_block_is_a_single_atom_with_one_line(self):
        data = sbs.generate(parse("C+(A+B+)C-A-B-"))  # 5 átomos: C+, (A+B+), C-, A-, B-
        pl_ids = {n["id"] for n in data["nodes"] if n["type"] == "PressureLine"}
        assert pl_ids == {f"gen-pl-step{k}" for k in range(5)}

    def test_memory_has_dedicated_pressure_source_and_exhaust(self):
        data = sbs.generate(parse("A+B+A-B-"))
        p_source = _conns_to(data, "gen-mc-0", "P")
        r_exhaust = _conns_from(data, "gen-mc-0", "R")
        assert len(p_source) == 1 and p_source[0]["source"]["node"] != "gen-mc-0"
        assert len(r_exhaust) == 1

    def test_memory_output_feeds_its_own_line(self):
        data = sbs.generate(parse("A+B+A-B-"))
        conns = _conns_from(data, "gen-mc-0", "A")
        assert len(conns) == 1
        assert conns[0]["target"]["node"] == "gen-pl-step0"

    def test_button_sets_only_atom_zero(self):
        data = sbs.generate(parse("A+B+A-B-"))
        conns = _conns_from(data, "gen-btn", "A")
        assert len(conns) == 1
        assert conns[0]["target"]["node"] == "gen-mc-0"
        assert conns[0]["target"]["anchor"] == "PL"

    def test_reset_ring_wraps_last_atom_to_first_line(self):
        data = sbs.generate(parse("A+B+A-B-"))  # 4 átomos: 0,1,2,3
        for k in range(4):
            expected_source_pl = f"gen-pl-step{(k + 1) % 4}"
            conns = _conns_to(data, f"gen-mc-{k}", "PR")
            assert len(conns) == 1
            assert conns[0]["source"]["node"] == expected_source_pl

    def test_last_memory_defaults_active_all_others_rest(self):
        data = sbs.generate(parse("A+B+A-B-"))
        mc = {n["id"]: n for n in data["nodes"] if n["id"].startswith("gen-mc-")}
        assert mc["gen-mc-3"]["properties"]["default_side"] == "left"
        for k in range(3):
            assert mc[f"gen-mc-{k}"]["properties"]["default_side"] == "right"


class TestPilotWiring:
    """Cada evento do átomo aciona o pilot da sua 4/2 direto da linha do
    átomo -- inclusive em blocos paralelos, sem duplicação."""

    def test_single_event_atom_triggers_its_pilot(self):
        data = sbs.generate(parse("A+B+A-B-"))
        conns = _conns_to(data, "gen-v42-A", "PL")
        assert len(conns) == 1
        assert conns[0]["source"]["node"] == "gen-pl-step0"

    def test_retraction_uses_pr_pilot(self):
        data = sbs.generate(parse("A+B+A-B-"))
        conns = _conns_to(data, "gen-v42-A", "PR")
        assert len(conns) == 1
        assert conns[0]["source"]["node"] == "gen-pl-step2"

    def test_parallel_block_feeds_both_pilots_from_same_line_no_duplication(self):
        data = sbs.generate(parse("C+(A+B+)C-A-B-"))  # bloco (A+B+) é o átomo 1
        a_pl = _conns_to(data, "gen-v42-A", "PL")
        b_pl = _conns_to(data, "gen-v42-B", "PL")
        assert len(a_pl) == 1 and a_pl[0]["source"]["node"] == "gen-pl-step1"
        assert len(b_pl) == 1 and b_pl[0]["source"]["node"] == "gen-pl-step1"
