"""Testes unitários para o módulo sequence_parser."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.sequence_parser import parse, extract_cylinders, split_into_groups, validate_cylinder_states


# ---------------------------------------------------------------------------
# validate_cylinder_states()
# ---------------------------------------------------------------------------

class TestValidateCylinderStates:
    def test_valid_starts_retracted(self):
        validate_cylinder_states([("A","+"), ("B","+"), ("A","-"), ("B","-")])

    def test_valid_starts_extended(self):
        # cilindro começa avançado: primeiro movimento é retração
        validate_cylinder_states([("A","-"), ("B","+"), ("A","+"), ("B","-")])

    def test_valid_single_cylinder_retracted_start(self):
        validate_cylinder_states([("A","+"), ("A","-")])

    def test_valid_single_cylinder_extended_start(self):
        validate_cylinder_states([("A","-"), ("A","+")])

    def test_valid_three_cylinders(self):
        validate_cylinder_states([("A","+"), ("B","+"), ("C","+"), ("A","-"), ("B","-"), ("C","-")])

    def test_accepts_events_with_parallel_id_field(self):
        validate_cylinder_states([("A","+",0), ("B","+",0), ("A","-",None), ("B","-",None)])

    def test_invalid_consecutive_same_direction_extend(self):
        with pytest.raises(ValueError, match="estendido"):
            validate_cylinder_states([("A","+"), ("B","+"), ("A","+"), ("B","-"), ("A","-")])

    def test_invalid_consecutive_same_direction_retract(self):
        with pytest.raises(ValueError, match="retraído"):
            validate_cylinder_states([("A","+"), ("A","-"), ("B","+"), ("A","-"), ("B","-")])

    def test_invalid_does_not_close_cycle(self):
        # A começa com + mas termina com + (ímpar de movimentos)
        with pytest.raises(ValueError, match="não fecha o ciclo"):
            validate_cylinder_states([("A","+"), ("B","+"), ("A","-"), ("B","-"), ("A","+")])

    def test_invalid_mixed_start_does_not_close(self):
        # A começa retraído ("+"), B começa avançado ("-"); B não fecha
        with pytest.raises(ValueError, match="não fecha o ciclo"):
            validate_cylinder_states([("A","+"), ("B","-"), ("A","-")])


# ---------------------------------------------------------------------------
# parse() — inclui validação
# ---------------------------------------------------------------------------

class TestParse:
    def test_basic_retracted_start(self):
        assert parse("A+B+A-B-") == [
            ("A","+",None), ("B","+",None), ("A","-",None), ("B","-",None),
        ]

    def test_basic_extended_start(self):
        assert parse("A-B+A+B-") == [
            ("A","-",None), ("B","+",None), ("A","+",None), ("B","-",None),
        ]

    def test_single_cylinder_valid(self):
        assert parse("A+A-") == [("A","+",None), ("A","-",None)]

    def test_multi_letter_cylinder(self):
        assert parse("Ab+Ab-") == [("Ab","+",None), ("Ab","-",None)]

    def test_ignores_spaces(self):
        assert parse("A+ B+ A- B-") == [
            ("A","+",None), ("B","+",None), ("A","-",None), ("B","-",None),
        ]

    def test_raises_on_empty(self):
        with pytest.raises(ValueError):
            parse("")

    def test_raises_on_no_valid_token(self):
        with pytest.raises(ValueError):
            parse("abc123")

    def test_raises_on_consecutive_same_direction(self):
        with pytest.raises(ValueError):
            parse("A+B+A+A-B-A-")

    def test_raises_on_open_cycle(self):
        with pytest.raises(ValueError, match="não fecha o ciclo"):
            parse("A+B+B-")

    def test_multi_cycle_without_parentheses_still_valid(self):
        # Regressão: dois ciclos do mesmo cilindro (A) já eram aceitos antes
        # deste plano e continuam sendo — parênteses não são exigidos aqui.
        assert parse("A+B+A-B-A+A-") == [
            ("A","+",None), ("B","+",None), ("A","-",None),
            ("B","-",None), ("A","+",None), ("A","-",None),
        ]


class TestParseParallelGroups:
    def test_simple_block(self):
        assert parse("(A+B+)A-B-") == [
            ("A","+",0), ("B","+",0), ("A","-",None), ("B","-",None),
        ]

    def test_single_event_block_unwraps_to_sequential(self):
        assert parse("(A+)A-") == parse("A+A-")

    def test_single_event_block_does_not_consume_a_visible_id(self):
        events = parse("(A+B+)C+(A-)B-C-")
        # primeiro bloco (2 eventos) usa parallel_id=0; o segundo bloco tem
        # 1 evento só -> desembrulha para parallel_id=None, não "1"
        assert events == [
            ("A","+",0), ("B","+",0), ("C","+",None),
            ("A","-",None), ("B","-",None), ("C","-",None),
        ]

    def test_second_multi_event_block_gets_incremented_id(self):
        events = parse("(A+B+)C+(A-B-)C-")
        # dois blocos com 2+ eventos cada -> parallel_id 0 e 1, em ordem
        assert events == [
            ("A","+",0), ("B","+",0), ("C","+",None),
            ("A","-",1), ("B","-",1), ("C","-",None),
        ]

    def test_duplicate_letter_in_block_raises(self):
        with pytest.raises(ValueError, match="repetido dentro do mesmo grupo simultâneo"):
            parse("(A+A-)")

    def test_nested_parentheses_raises(self):
        with pytest.raises(ValueError, match="aninhados"):
            parse("(A+(B+C+))")

    def test_unbalanced_missing_close_raises(self):
        with pytest.raises(ValueError, match=r"'\(' sem '\)' correspondente"):
            parse("(A+B+")

    def test_unbalanced_missing_open_raises(self):
        with pytest.raises(ValueError, match=r"'\)' sem '\(' correspondente"):
            parse("A+B+)")


# ---------------------------------------------------------------------------
# extract_cylinders()
# ---------------------------------------------------------------------------

class TestExtractCylinders:
    def test_order_of_first_appearance(self):
        events = [("A","+"), ("B","+"), ("A","-"), ("B","-")]
        assert extract_cylinders(events) == ["A", "B"]

    def test_single(self):
        assert extract_cylinders([("A","+"), ("A","-")]) == ["A"]

    def test_three_cylinders(self):
        events = [("A","+"), ("B","+"), ("C","+"), ("A","-"), ("B","-"), ("C","-")]
        assert extract_cylinders(events) == ["A", "B", "C"]

    def test_accepts_events_with_parallel_id_field(self):
        events = [("A","+",0), ("B","+",0), ("A","-",None), ("B","-",None)]
        assert extract_cylinders(events) == ["A", "B"]

    def test_preserves_order_not_alphabetical(self):
        events = [("C","+"), ("A","+"), ("C","-"), ("A","-")]
        assert extract_cylinders(events) == ["C", "A"]


# ---------------------------------------------------------------------------
# split_into_groups()
# ---------------------------------------------------------------------------

class TestSplitIntoGroups:
    def test_two_groups_classic(self):
        events = [("A","+"), ("B","+"), ("A","-"), ("B","-")]
        assert split_into_groups(events) == [
            [("A","+"), ("B","+")],
            [("A","-"), ("B","-")],
        ]

    def test_single_group(self):
        events = [("A","+"), ("B","+"), ("C","+")]
        assert split_into_groups(events) == [[("A","+"), ("B","+"), ("C","+")]]

    def test_four_groups(self):
        events = [("A","+"), ("A","-"), ("A","+"), ("A","-")]
        assert split_into_groups(events) == [
            [("A","+")], [("A","-")], [("A","+")], [("A","-")],
        ]

    def test_three_cylinders_two_groups(self):
        events = [("A","+"), ("B","+"), ("C","+"), ("A","-"), ("B","-"), ("C","-")]
        assert split_into_groups(events) == [
            [("A","+"), ("B","+"), ("C","+")],
            [("A","-"), ("B","-"), ("C","-")],
        ]

    def test_asymmetric_split(self):
        events = [("A","+"), ("B","+"), ("A","-"), ("B","-"), ("A","+"), ("A","-")]
        assert split_into_groups(events) == [
            [("A","+"), ("B","+")],
            [("A","-"), ("B","-")],
            [("A","+")],
            [("A","-")],
        ]

    def test_atomic_block_cuts_before_whole_block_not_inside(self):
        # "A" já está no grupo corrente quando o bloco (A-,B+) começa.
        # O corte deve acontecer ANTES do bloco inteiro — nunca separando
        # A de B dentro dele.
        events = [
            ("A", "+", None),
            ("A", "-", 0), ("B", "+", 0),
            ("B", "-", None),
        ]
        assert split_into_groups(events) == [
            [("A", "+", None)],
            [("A", "-", 0), ("B", "+", 0)],
            [("B", "-", None)],
        ]

    def test_block_with_no_collision_merges_into_current_group(self):
        events = [
            ("C", "+", None),
            ("A", "-", 0), ("B", "+", 0),
        ]
        assert split_into_groups(events) == [
            [("C", "+", None), ("A", "-", 0), ("B", "+", 0)],
        ]