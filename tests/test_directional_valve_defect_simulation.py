import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways


def _make_valve(k=1e-7, body_state=0):
    valve = Valve_4_2_Ways("v42", domain="hydraulic", properties={"k": k})
    valve.body_state = body_state
    for port in ("P", "A", "B", "R"):
        valve.add_anchor(port, domain="hydraulic")
        valve.anchors[port].pressure_var = f"P_{port}"
    return valve


def test_fresh_instance_has_no_defect():
    valve = _make_valve()
    assert valve.defect_active is False
    assert valve._stuck_defect is False


def test_set_defect_changes_k():
    valve = _make_valve(k=1e-7)
    valve.handle_command({"action": "set_defect", "k": 5e-8, "stuck": False})
    assert valve.k == 5e-8
    assert valve.defect_active is True


def test_set_defect_sets_stuck_flag():
    valve = _make_valve()
    valve.handle_command({"action": "set_defect", "k": valve.k, "stuck": True})
    assert valve._stuck_defect is True
    assert valve.defect_active is True


def test_clear_defect_restores_original_k_and_unstucks():
    valve = _make_valve(k=1e-7)
    valve.handle_command({"action": "set_defect", "k": 5e-8, "stuck": True})
    valve.handle_command({"action": "clear_defect"})
    assert valve.k == 1e-7
    assert valve._stuck_defect is False
    assert valve.defect_active is False


def test_stuck_defect_freezes_body_state_despite_actuator_commands():
    valve = _make_valve(body_state=0)
    valve.handle_command({"action": "set_defect", "k": valve.k, "stuck": True})
    valve.handle_command({"type": "actuator", "side": "left", "value": 1})
    valve.update()
    assert valve.body_state == 0  # continua travada, ignora bits["left"]=1


def test_unstuck_valve_still_reacts_normally_to_actuator_commands():
    valve = _make_valve(body_state=0)
    valve.handle_command({"type": "actuator", "side": "left", "value": 1})
    valve.update()
    assert valve.body_state == 1


def test_stuck_defect_applies_even_without_k_attribute_pneumatic_domain():
    """stuck é independente de k -- k só existe em domínio hidráulico, mas o
    domínio de simulação não impede stuck em pneumático (a UI é quem restringe
    a exposição desse defeito a hidráulico, ver Task 4)."""
    valve = Valve_4_2_Ways("v42", domain="pneumatic", properties={})
    valve.handle_command({"action": "set_defect", "k": 999.0, "stuck": True})
    assert not hasattr(valve, "k")
    assert valve._stuck_defect is True


def test_unknown_action_is_noop():
    valve = _make_valve()
    original_k = valve.k
    valve.handle_command({"action": "does_not_exist"})
    assert valve.k == original_k
    assert valve._stuck_defect is False


def test_new_instance_never_inherits_defect_from_a_previous_one():
    stale = _make_valve()
    stale.handle_command({"action": "set_defect", "k": 1e-9, "stuck": True})
    fresh = _make_valve()
    assert fresh.defect_active is False
    assert fresh._stuck_defect is False
