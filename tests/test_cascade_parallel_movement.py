"""Testes de topologia para o suporte a movimento simultâneo (AndValve) em
cascade.py — ver
docs/superpowers/specs/2026-07-10-cascade-parallel-movement-design.md
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.sequence_parser import parse
from circuit_generator.methods import cascade
from circuit_generator.methods.cascade import _atomize_group


class TestAtomizeGroup:
    def test_no_parallel_ids_each_event_is_its_own_atom(self):
        group = [("A", "+", None), ("B", "+", None)]
        assert _atomize_group(group) == [
            [(0, "A", "+")],
            [(1, "B", "+")],
        ]

    def test_two_tuples_without_parallel_id_field(self):
        # split_into_groups pode devolver 2-tuplas quando chamado direto
        # (fora de parse()) -- _atomize_group precisa tolerar isso.
        group = [("A", "+"), ("B", "+")]
        assert _atomize_group(group) == [
            [(0, "A", "+")],
            [(1, "B", "+")],
        ]

    def test_single_block_is_one_atom(self):
        group = [("A", "+", 0), ("B", "+", 0)]
        assert _atomize_group(group) == [
            [(0, "A", "+"), (1, "B", "+")],
        ]

    def test_event_then_block(self):
        group = [("C", "+", None), ("A", "+", 0), ("B", "+", 0)]
        assert _atomize_group(group) == [
            [(0, "C", "+")],
            [(1, "A", "+"), (2, "B", "+")],
        ]

    def test_two_blocks_in_sequence(self):
        group = [("A", "+", 0), ("B", "+", 0), ("C", "+", 1), ("D", "+", 1)]
        assert _atomize_group(group) == [
            [(0, "A", "+"), (1, "B", "+")],
            [(2, "C", "+"), (3, "D", "+")],
        ]

    def test_block_then_event_then_block(self):
        group = [
            ("A", "+", 0), ("B", "+", 0),
            ("C", "+", None),
            ("D", "+", 1), ("E", "+", 1),
        ]
        assert _atomize_group(group) == [
            [(0, "A", "+"), (1, "B", "+")],
            [(2, "C", "+")],
            [(3, "D", "+"), (4, "E", "+")],
        ]
