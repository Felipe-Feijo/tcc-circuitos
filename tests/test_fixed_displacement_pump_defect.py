import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from main_window.language import language_manager
from tests.defect_test_helpers import form_label_texts
from graphics.items.base.nodes.pumps.fixed_displacement_pump import (
    FixedDisplacementPump as FixedDisplacementPumpItem,
)
from simulation.connections import Connection
from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
from simulation.nodes.reservoir import Reservoir
from simulation.nodes.throttle_valve import ThrottleValve
from simulation.simulation_engine import SimulationEngine

Q = 1e-4
K = 1e-7


def _pump(q=Q):
    p = FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": q})
    p.add_anchor("P", domain="hydraulic")
    p.add_anchor("S", domain="hydraulic")
    return p


def test_fresh_pump_has_no_defect():
    assert _pump().defect_active is False


def test_set_defect_changes_q_and_marks_active():
    p = _pump()
    p.handle_command({"action": "set_defect", "Q": Q * 0.6})
    assert p.Q_set == pytest.approx(Q * 0.6)
    assert p.defect_active is True


def test_clear_defect_restores_q():
    p = _pump()
    p.handle_command({"action": "set_defect", "Q": Q * 0.6})
    p.handle_command({"action": "clear_defect"})
    assert p.Q_set == Q
    assert p.defect_active is False


def _circuit():
    pump = _pump()
    tv = ThrottleValve("tv", domain="hydraulic", properties={"k": K})
    tv.add_anchor("X", domain="hydraulic")
    tv.add_anchor("Y", domain="hydraulic")
    res_s = Reservoir("res_s", domain="hydraulic", properties={"pressure": 0.0})
    res_s.add_anchor("T", domain="hydraulic")
    res_t = Reservoir("res_t", domain="hydraulic", properties={"pressure": 0.0})
    res_t.add_anchor("T", domain="hydraulic")
    conns = [
        Connection(pump.get_anchor("P"), tv.get_anchor("X")),
        Connection(tv.get_anchor("Y"), res_t.get_anchor("T")),
        Connection(pump.get_anchor("S"), res_s.get_anchor("T")),
    ]
    nodes = {"pump": pump, "tv": tv, "res_s": res_s, "res_t": res_t}
    return SimulationEngine(nodes, {c.id: c for c in conns}), pump, tv


def test_defect_applied_mid_run_lowers_flow_then_clear_restores():
    """Worn pump: delivers less flow, so the downstream orifice sees a
    smaller drop ((Q/k)^2)."""
    engine, pump, tv = _circuit()
    engine.run_until_stable(dt=1.0)
    assert tv.get_anchor("X").flow == pytest.approx(Q, rel=0.02)
    healthy_p = pump.get_anchor("P").pressure

    pump.handle_command({"action": "set_defect", "Q": Q * 0.6})
    engine.run_until_stable(dt=1.0)
    assert tv.get_anchor("X").flow == pytest.approx(Q * 0.6, rel=0.02)
    assert pump.get_anchor("P").pressure == pytest.approx((Q * 0.6 / K) ** 2, rel=0.02)
    assert pump.get_anchor("P").pressure < healthy_p

    pump.handle_command({"action": "clear_defect"})
    engine.run_until_stable(dt=1.0)
    assert tv.get_anchor("X").flow == pytest.approx(Q, rel=0.02)
    assert pump.get_anchor("P").pressure == pytest.approx(healthy_p, rel=0.02)


def test_item_defect_fields_one_spec():
    specs = FixedDisplacementPumpItem(domain="hydraulic").defect_fields()
    assert [s.key for s in specs] == ["Q"]
    assert specs[0].kind == "number"
    assert specs[0].min_value == 0
    assert specs[0].label == "Flow rate (m³/s)"
    assert specs[0].placeholder == "ex: 8.3e-4  (= 50 L/min)"


def test_item_dialog_prefilled_from_properties_before_sync():
    item = FixedDisplacementPumpItem(domain="hydraulic")
    item.properties["Q"] = 2e-4
    dialog = item.build_defect_dialog()
    assert float(dialog.defect_widget("Q").text()) == 2e-4


def test_item_dialog_prefilled_from_live_domain_node():
    item = FixedDisplacementPumpItem(domain="hydraulic")
    item.properties["Q"] = Q
    node = _pump()
    item.command.connect(lambda nid, payload: node.handle_command(payload))
    item.update_from_domain(node)
    node.handle_command({"action": "set_defect", "Q": 4e-5})
    dialog = item.build_defect_dialog()
    assert float(dialog.defect_widget("Q").text()) == 4e-5


def test_item_apply_defect_emits_set_defect_float():
    item = FixedDisplacementPumpItem(domain="hydraulic")
    item.properties["Q"] = Q
    dialog = item.build_defect_dialog()
    dialog.defect_widget("Q").setText("4e-5")
    received = []
    item.command.connect(lambda nid, payload: received.append(payload))
    item.apply_defect_from_dialog(dialog)
    assert received == [{"action": "set_defect", "Q": 4e-5}]


def test_item_defect_dialog_label_translates_to_pt_br():
    item = FixedDisplacementPumpItem(domain="hydraulic")
    item.properties["Q"] = Q
    language_manager.apply_language(app, "pt_BR")
    try:
        dialog = item.build_defect_dialog()
        try:
            assert "Vazão (m³/s)" in form_label_texts(dialog)
        finally:
            dialog.close()
    finally:
        language_manager.apply_language(app, "en")
