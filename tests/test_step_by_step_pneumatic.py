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
