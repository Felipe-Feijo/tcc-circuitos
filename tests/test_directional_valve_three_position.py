import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.nodes.directional_valve.directional_valve import DirectionalValve


class _ThreePositionValve(DirectionalValve):
    """Subclasse mínima só para exercitar THREE_POSITION=True no __init__
    real (Valve_4_3_Ways, criada na Task 2, é a versão de produção disso)."""
    THREE_POSITION = True


def make_three_position(actuators=None):
    return _ThreePositionValve(
        "v43", "test_three_position",
        domain=None,
        properties={"actuators": actuators or {"left": None, "right": None}},
    )


def test_three_position_default_class_attribute_is_false():
    valve = DirectionalValve(
        "v42", "test_two_position", domain=None,
        properties={"actuators": {"left": None, "right": None}},
    )
    assert valve.THREE_POSITION is False


def test_three_position_initial_state_is_center_regardless_of_default_side():
    valve = _ThreePositionValve(
        "v43", "test_three_position", domain=None,
        properties={
            "actuators": {"left": None, "right": None},
            "default_side": "left",  # deve ser ignorado
        },
    )
    assert valve.body_state == 1


def test_three_position_left_bit_alone_moves_to_state_2():
    valve = make_three_position()
    valve.bits = {"left": 1, "right": 0}
    valve._compute_body_state()
    assert valve.body_state == 2


def test_three_position_right_bit_alone_moves_to_state_0():
    valve = make_three_position()
    valve.bits = {"left": 0, "right": 1}
    valve._compute_body_state()
    assert valve.body_state == 0


def test_three_position_no_bits_centers():
    valve = make_three_position()
    valve.body_state = 2  # estado anterior qualquer
    valve.bits = {"left": 0, "right": 0}
    valve._compute_body_state()
    assert valve.body_state == 1


def test_three_position_both_bits_centers_springs_cancel_pilots():
    valve = make_three_position()
    valve.body_state = 2  # estado anterior qualquer
    valve.bits = {"left": 1, "right": 1}
    valve._compute_body_state()
    assert valve.body_state == 1


def test_two_position_unaffected_00_and_11_still_keep_previous_state():
    valve = DirectionalValve(
        "v42", "test_two_position", domain=None,
        properties={"actuators": {"left": None, "right": None}},
    )
    valve.body_state = 1
    valve.bits = {"left": 0, "right": 0}
    valve._compute_body_state()
    assert valve.body_state == 1  # mantém -- comportamento antigo intacto

    valve.body_state = 0
    valve.bits = {"left": 1, "right": 1}
    valve._compute_body_state()
    assert valve.body_state == 0  # mantém -- comportamento antigo intacto
