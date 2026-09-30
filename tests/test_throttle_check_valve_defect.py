import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from main_window.language import language_manager
from tests.defect_test_helpers import form_label_texts
from graphics.items.base.nodes.check_valve.throttle_check_valve import (
    ThrottleCheckValve as ThrottleCheckValveItem,
)
from simulation.connections import Connection
from simulation.nodes.check_valve.throttle_check_valve import ThrottleCheckValve
from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
from simulation.nodes.reservoir import Reservoir
from simulation.simulation_engine import SimulationEngine

K = 1e-7
Q = 1e-4
LABEL = "Conductance k (m³/s/√Pa) — restricted direction"


def _valve(k=K):
    v = ThrottleCheckValve("tcv", domain="hydraulic", properties={"k": k})
    v.add_anchor("X", domain="hydraulic")
    v.add_anchor("Y", domain="hydraulic")
    return v


def test_fresh_valve_has_no_defect():
    assert _valve().defect_active is False


def test_set_defect_changes_k_and_marks_active():
    v = _valve()
    v.handle_command({"action": "set_defect", "k": K * 0.3})
    assert v.k == pytest.approx(K * 0.3)
    assert v.defect_active is True


def test_clear_defect_restores_k():
    v = _valve()
    v.handle_command({"action": "set_defect", "k": K * 0.3})
    v.handle_command({"action": "clear_defect"})
    assert v.k == K
    assert v.defect_active is False


def test_pneumatic_set_defect_is_noop():
    v = ThrottleCheckValve("tcv", domain="pneumatic", properties={})
    v.add_anchor("X", domain="pneumatic")
    v.add_anchor("Y", domain="pneumatic")
    v.handle_command({"action": "set_defect", "k": 1e-8})
    assert v.defect_active is False
    assert not hasattr(v, "k")


def _circuit(feed_anchor):
    """Pump feeds feed_anchor (X = restricted, Y = free); the other side
    drains to a reservoir."""
    tcv = _valve()
    other = "Y" if feed_anchor == "X" else "X"
    pump = FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": Q})
    pump.add_anchor("P", domain="hydraulic")
    pump.add_anchor("S", domain="hydraulic")
    res_s = Reservoir("res_s", domain="hydraulic", properties={"pressure": 0.0})
    res_s.add_anchor("T", domain="hydraulic")
    res_t = Reservoir("res_t", domain="hydraulic", properties={"pressure": 0.0})
    res_t.add_anchor("T", domain="hydraulic")
    conns = [
        Connection(pump.get_anchor("P"), tcv.get_anchor(feed_anchor)),
        Connection(tcv.get_anchor(other), res_t.get_anchor("T")),
        Connection(pump.get_anchor("S"), res_s.get_anchor("T")),
    ]
    nodes = {"tcv": tcv, "pump": pump, "res_s": res_s, "res_t": res_t}
    return SimulationEngine(nodes, {c.id: c for c in conns}), tcv


def _drop(tcv):
    return tcv.get_anchor("X").pressure - tcv.get_anchor("Y").pressure


def test_restricted_direction_healthy_drop_follows_orifice():
    engine, tcv = _circuit("X")
    engine.run_until_stable(dt=1.0)
    assert _drop(tcv) == pytest.approx((Q / K) ** 2, rel=0.02)


def test_restricted_direction_defect_mid_run_raises_drop_then_clear_restores():
    engine, tcv = _circuit("X")
    engine.run_until_stable(dt=1.0)
    healthy = _drop(tcv)

    tcv.handle_command({"action": "set_defect", "k": K * 0.3})
    engine.run_until_stable(dt=1.0)
    assert _drop(tcv) == pytest.approx((Q / (K * 0.3)) ** 2, rel=0.02)
    assert _drop(tcv) > healthy * 5

    tcv.handle_command({"action": "clear_defect"})
    engine.run_until_stable(dt=1.0)
    assert _drop(tcv) == pytest.approx(healthy, rel=0.02)


def test_free_direction_unaffected_by_defect():
    engine, tcv = _circuit("Y")
    engine.run_until_stable(dt=1.0)
    assert _drop(tcv) == pytest.approx(0.0, abs=1e3)

    tcv.handle_command({"action": "set_defect", "k": K * 0.3})
    engine.run_until_stable(dt=1.0)
    assert _drop(tcv) == pytest.approx(0.0, abs=1e3)


def test_item_defect_fields_one_spec_in_hydraulic():
    specs = ThrottleCheckValveItem(domain="hydraulic").defect_fields()
    assert [s.key for s in specs] == ["k"]
    assert specs[0].kind == "number"
    assert specs[0].min_value == 0
    assert specs[0].label == LABEL
    assert specs[0].placeholder == "ex: 1.5e-8"


def test_item_defect_fields_empty_in_pneumatic():
    item = ThrottleCheckValveItem(domain="pneumatic")
    assert item.defect_fields() == []
    assert item.build_defect_dialog() is None


def test_item_dialog_prefilled_from_properties_before_sync():
    item = ThrottleCheckValveItem(domain="hydraulic")
    item.properties["k"] = 2e-7
    dialog = item.build_defect_dialog()
    assert float(dialog.defect_widget("k").text()) == 2e-7


def test_item_dialog_prefilled_from_live_domain_node():
    item = ThrottleCheckValveItem(domain="hydraulic")
    item.properties["k"] = K
    node = _valve()
    item.command.connect(lambda nid, payload: node.handle_command(payload))
    item.update_from_domain(node)
    node.handle_command({"action": "set_defect", "k": 3e-8})
    dialog = item.build_defect_dialog()
    assert float(dialog.defect_widget("k").text()) == 3e-8


def test_item_apply_defect_emits_set_defect_float():
    item = ThrottleCheckValveItem(domain="hydraulic")
    item.properties["k"] = K
    dialog = item.build_defect_dialog()
    dialog.defect_widget("k").setText("3e-8")
    received = []
    item.command.connect(lambda nid, payload: received.append(payload))
    item.apply_defect_from_dialog(dialog)
    assert received == [{"action": "set_defect", "k": 3e-8}]


def test_item_defect_dialog_label_translates_to_pt_br():
    item = ThrottleCheckValveItem(domain="hydraulic")
    item.properties["k"] = K
    language_manager.apply_language(app, "pt_BR")
    try:
        dialog = item.build_defect_dialog()
        try:
            assert "Condutância k (m³/s/√Pa) — sentido restrito" in form_label_texts(dialog)
        finally:
            dialog.close()
    finally:
        language_manager.apply_language(app, "en")
