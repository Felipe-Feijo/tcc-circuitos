import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from simulation.connections import Connection
from simulation.nodes.pilot_operated_relief_valve import PilotOperatedReliefValve
from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
from simulation.nodes.reservoir import Reservoir
from simulation.simulation_engine import SimulationEngine

P_SET = 1.0e7
P_VENT = 3.0e5


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------

def _valve(p_set=P_SET):
    v = PilotOperatedReliefValve("po", domain="hydraulic", properties={"p_set": p_set, "p_vent": P_VENT})
    for a in "PTX":
        v.add_anchor(a, domain="hydraulic")
    return v


def test_fresh_valve_has_no_defect():
    assert _valve().defect_active is False


def test_set_defect_changes_p_set_and_hint():
    v = _valve()
    v.handle_command({"action": "set_defect", "p_set": 5e6})
    assert v.p_set == 5e6
    assert v.p_hint == 5e6 + P_VENT
    assert v.defect_active is True


def test_clear_defect_restores_p_set():
    v = _valve()
    v.handle_command({"action": "set_defect", "p_set": 5e6})
    v.handle_command({"action": "clear_defect"})
    assert v.p_set == P_SET
    assert v.defect_active is False


def _circuit(q=1e-3):
    v = _valve()
    pump = FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": q})
    pump.add_anchor("P", domain="hydraulic")
    pump.add_anchor("S", domain="hydraulic")
    res_s = Reservoir("res_s", domain="hydraulic", properties={"pressure": 0.0})
    res_s.add_anchor("T", domain="hydraulic")
    res_t = Reservoir("res_t", domain="hydraulic", properties={"pressure": 0.0})
    res_t.add_anchor("T", domain="hydraulic")
    conns = [
        Connection(pump.get_anchor("P"), v.get_anchor("P")),
        Connection(pump.get_anchor("S"), res_s.get_anchor("T")),
        Connection(v.get_anchor("T"), res_t.get_anchor("T")),
    ]
    nodes = {"po": v, "pump": pump, "res_s": res_s, "res_t": res_t}
    return SimulationEngine(nodes, {c.id: c for c in conns}), v


@pytest.mark.parametrize("factor", [0.5, 1.5])
def test_defect_applied_and_cleared_mid_run(factor):
    engine, v = _circuit()
    engine.run_until_stable(dt=1.0)
    assert v.get_anchor("P").pressure == pytest.approx(P_SET + P_VENT, rel=1e-3)

    v.handle_command({"action": "set_defect", "p_set": P_SET * factor})
    engine.run_until_stable(dt=1.0)
    assert v.get_anchor("P").pressure == pytest.approx(P_SET * factor + P_VENT, rel=1e-3)

    v.handle_command({"action": "clear_defect"})
    engine.run_until_stable(dt=1.0)
    assert v.get_anchor("P").pressure == pytest.approx(P_SET + P_VENT, rel=1e-3)


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.pilot_operated_relief_valve import PilotOperatedReliefValve as Item


def test_item_defect_fields_one_spec_in_hydraulic():
    specs = Item(domain="hydraulic").defect_fields()
    assert [s.key for s in specs] == ["p_set"]
    assert specs[0].kind == "number"
    assert specs[0].min_value == 0
    assert specs[0].label == "Pilot setting p_set (Pa)"


def test_item_apply_defect_emits_set_defect_float():
    item = Item(domain="hydraulic")
    item.properties["p_set"] = P_SET
    dialog = item.build_defect_dialog()
    dialog.defect_widget("p_set").setText("5e6")
    received = []
    item.command.connect(lambda nid, payload: received.append(payload))
    item.apply_defect_from_dialog(dialog)
    assert received == [{"action": "set_defect", "p_set": 5e6}]
