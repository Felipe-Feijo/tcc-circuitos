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
        assert parse("A+B+A-B-") == [("A","+"), ("B","+"), ("A","-"), ("B","-")]

    def test_basic_extended_start(self):
        assert parse("A-B+A+B-") == [("A","-"), ("B","+"), ("A","+"), ("B","-")]

    def test_single_cylinder_valid(self):
        assert parse("A+A-") == [("A","+"), ("A","-")]

    def test_multi_letter_cylinder(self):
        assert parse("Ab+Ab-") == [("Ab","+"), ("Ab","-")]

    def test_ignores_spaces(self):
        assert parse("A+ B+ A- B-") == [("A","+"), ("B","+"), ("A","-"), ("B","-")]

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