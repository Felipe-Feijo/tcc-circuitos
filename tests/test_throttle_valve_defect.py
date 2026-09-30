import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from main_window.language import language_manager
from tests.defect_test_helpers import form_label_texts
from graphics.items.base.nodes.throttle_valve import ThrottleValve as ThrottleValveItem
from simulation.connections import Connection
from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
from simulation.nodes.reservoir import Reservoir
from simulation.nodes.throttle_valve import ThrottleValve
from simulation.simulation_engine import SimulationEngine

K = 1e-7
Q = 1e-4


def _valve(k=K):
    v = ThrottleValve("tv", domain="hydraulic", properties={"k": k})
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


def _circuit():
    tv = _valve()
    pump = FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": Q})
    pump.add_anchor("P", domain="hydraulic")
    pump.add_anchor("S", domain="hydraulic")
    res_s = Reservoir("res_s", domain="hydraulic", properties={"pressure": 0.0})
    res_s.add_anchor("T", domain="hydraulic")
    res_t = Reservoir("res_t", domain="hydraulic", properties={"pressure": 0.0})
    res_t.add_anchor("T", domain="hydraulic")
    conns = [
        Connection(pump.get_anchor("P"), tv.get_anchor("X")),
        Connection(tv.get_anchor("Y"), res_t.get_anchor("T")),
        Connection(pump.get_anchor("S"), res_s.get_anchor("T")),
    ]
    nodes = {"tv": tv, "pump": pump, "res_s": res_s, "res_t": res_t}
    return SimulationEngine(nodes, {c.id: c for c in conns}), tv


def _drop(tv):
    return tv.get_anchor("X").pressure - tv.get_anchor("Y").pressure


def test_healthy_drop_follows_orifice_equation():
    engine, tv = _circuit()
    engine.run_until_stable(dt=1.0)
    assert _drop(tv) == pytest.approx((Q / K) ** 2, rel=0.02)


def test_defect_applied_mid_run_raises_drop_then_clear_restores():
    """Fixed pump flow: a clogged orifice (smaller k) needs a larger drop.
    The pressure scale is rebuilt from live hints each round, so the change
    is picked up on the next solve."""
    engine, tv = _circuit()
    engine.run_until_stable(dt=1.0)
    healthy = _drop(tv)

    tv.handle_command({"action": "set_defect", "k": K * 0.3})
    engine.run_until_stable(dt=1.0)
    assert _drop(tv) == pytest.approx((Q / (K * 0.3)) ** 2, rel=0.02)
    assert _drop(tv) > healthy * 5
    assert tv.get_anchor("X").flow == pytest.approx(Q, rel=0.02)

    tv.handle_command({"action": "clear_defect"})
    engine.run_until_stable(dt=1.0)
    assert _drop(tv) == pytest.approx(healthy, rel=0.02)


def test_item_defect_fields_one_spec_in_hydraulic():
    specs = ThrottleValveItem(domain="hydraulic").defect_fields()
    assert [s.key for s in specs] == ["k"]
    assert specs[0].kind == "number"
    assert specs[0].min_value == 0
    assert specs[0].label == "Conductance k (m³/s/√Pa)"
    assert specs[0].placeholder == "ex: 1.5e-8"


def test_item_dialog_prefilled_from_properties_before_sync():
    item = ThrottleValveItem(domain="hydraulic")
    item.properties["k"] = 2e-7
    dialog = item.build_defect_dialog()
    assert float(dialog.defect_widget("k").text()) == 2e-7


def test_item_dialog_prefilled_from_live_domain_node():
    item = ThrottleValveItem(domain="hydraulic")
    item.properties["k"] = K
    node = _valve()
    item.command.connect(lambda nid, payload: node.handle_command(payload))
    item.update_from_domain(node)
    node.handle_command({"action": "set_defect", "k": 3e-8})
    dialog = item.build_defect_dialog()
    assert float(dialog.defect_widget("k").text()) == 3e-8


def test_item_apply_defect_emits_set_defect_float():
    item = ThrottleValveItem(domain="hydraulic")
    item.properties["k"] = K
    dialog = item.build_defect_dialog()
    dialog.defect_widget("k").setText("3e-8")
    received = []
    item.command.connect(lambda nid, payload: received.append(payload))
    item.apply_defect_from_dialog(dialog)
    assert received == [{"action": "set_defect", "k": 3e-8}]


def test_item_defect_dialog_label_translates_to_pt_br():
    item = ThrottleValveItem(domain="hydraulic")
    item.properties["k"] = K
    language_manager.apply_language(app, "pt_BR")
    try:
        dialog = item.build_defect_dialog()
        try:
            assert "Condutância k (m³/s/√Pa)" in form_label_texts(dialog)
        finally:
            dialog.close()
    finally:
        language_manager.apply_language(app, "en")
