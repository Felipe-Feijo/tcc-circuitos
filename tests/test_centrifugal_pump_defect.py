import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import math

import pytest
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from main_window.language import language_manager
from tests.defect_test_helpers import form_label_texts
from graphics.items.base.nodes.pumps.centrifugal_pump import (
    CentrifugalPump as CentrifugalPumpItem,
)
from simulation.connections import Connection
from simulation.nodes.pumps.centrifugal_pump import CentrifugalPump
from simulation.nodes.reservoir import Reservoir
from simulation.nodes.throttle_valve import ThrottleValve
from simulation.simulation_engine import SimulationEngine

H = 2e6
Q_MAX = 2e-4
K = 1e-7


def _pump(h=H, q_max=Q_MAX):
    p = CentrifugalPump(
        "pump", domain="hydraulic", properties={"H_shutoff": h, "Q_max": q_max}
    )
    p.add_anchor("P", domain="hydraulic")
    p.add_anchor("S", domain="hydraulic")
    return p


def _operating_flow(h, q_max, k=K):
    # Pump curve h*(1-(Q/q_max)^2) meets orifice (Q/k)^2:
    # Q^2 * (1/k^2 + h/q_max^2) = h
    return math.sqrt(h / (1 / k ** 2 + h / q_max ** 2))


def test_fresh_pump_has_no_defect():
    assert _pump().defect_active is False


def test_set_defect_changes_both_fields_and_marks_active():
    p = _pump()
    p.handle_command({"action": "set_defect", "Q_max": Q_MAX * 0.5, "H_shutoff": H * 0.7})
    assert p.Q_max == pytest.approx(Q_MAX * 0.5)
    assert p.H_shutoff == pytest.approx(H * 0.7)
    assert p.defect_active is True


def test_clear_defect_restores_both_fields():
    p = _pump()
    p.handle_command({"action": "set_defect", "Q_max": Q_MAX * 0.5, "H_shutoff": H * 0.7})
    p.handle_command({"action": "clear_defect"})
    assert p.Q_max == Q_MAX
    assert p.H_shutoff == H
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


def test_defect_applied_mid_run_shifts_operating_point_then_clear_restores():
    """Worn impeller: the pump curve shrinks, so the operating point
    against the same orifice drops."""
    engine, pump, tv = _circuit()
    engine.run_until_stable(dt=1.0)
    healthy_q = tv.get_anchor("X").flow
    assert healthy_q == pytest.approx(_operating_flow(H, Q_MAX), rel=0.02)

    pump.handle_command({"action": "set_defect", "Q_max": Q_MAX * 0.5, "H_shutoff": H * 0.7})
    engine.run_until_stable(dt=1.0)
    worn_q = tv.get_anchor("X").flow
    assert worn_q == pytest.approx(_operating_flow(H * 0.7, Q_MAX * 0.5), rel=0.02)
    assert worn_q < healthy_q

    pump.handle_command({"action": "clear_defect"})
    engine.run_until_stable(dt=1.0)
    assert tv.get_anchor("X").flow == pytest.approx(healthy_q, rel=0.02)


def test_item_defect_fields_two_specs():
    specs = CentrifugalPumpItem(domain="hydraulic").defect_fields()
    assert [s.key for s in specs] == ["H_shutoff", "Q_max"]
    assert all(s.kind == "number" and s.min_value == 0 for s in specs)
    assert specs[0].label == "Shutoff pressure H (Pa)"
    assert specs[1].label == "Maximum flow Q_max (m³/s)"


def test_item_dialog_prefilled_from_live_domain_node():
    item = CentrifugalPumpItem(domain="hydraulic")
    item.properties.update({"H_shutoff": H, "Q_max": Q_MAX})
    node = _pump()
    item.command.connect(lambda nid, payload: node.handle_command(payload))
    item.update_from_domain(node)
    node.handle_command({"action": "set_defect", "Q_max": 1e-4})
    dialog = item.build_defect_dialog()
    assert float(dialog.defect_widget("Q_max").text()) == 1e-4
    assert float(dialog.defect_widget("H_shutoff").text()) == H


def test_item_apply_defect_emits_set_defect_floats():
    item = CentrifugalPumpItem(domain="hydraulic")
    item.properties.update({"H_shutoff": H, "Q_max": Q_MAX})
    dialog = item.build_defect_dialog()
    dialog.defect_widget("Q_max").setText("1e-4")
    received = []
    item.command.connect(lambda nid, payload: received.append(payload))
    item.apply_defect_from_dialog(dialog)
    assert received == [{"action": "set_defect", "H_shutoff": H, "Q_max": 1e-4}]


def test_item_defect_dialog_labels_translate_to_pt_br():
    item = CentrifugalPumpItem(domain="hydraulic")
    item.properties.update({"H_shutoff": H, "Q_max": Q_MAX})
    language_manager.apply_language(app, "pt_BR")
    try:
        dialog = item.build_defect_dialog()
        try:
            labels = form_label_texts(dialog)
            assert "Pressão de shutoff H (Pa)" in labels
            assert "Vazão máxima Q_max (m³/s)" in labels
        finally:
            dialog.close()
    finally:
        language_manager.apply_language(app, "en")
