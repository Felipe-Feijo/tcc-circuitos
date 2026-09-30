import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from main_window.language import language_manager
from graphics.items.base.nodes.pressure_reducing_valve import PressureReducingValve as PressureReducingValveItem
from simulation.connections import Connection
from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
from simulation.nodes.pressure_reducing_valve import PressureReducingValve
from simulation.nodes.reservoir import Reservoir
from simulation.simulation_engine import SimulationEngine


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------

def _prv(p_set=1.5e7):
    v = PressureReducingValve("prv", domain="hydraulic", properties={"p_set": p_set})
    v.add_anchor("P", domain="hydraulic")
    v.add_anchor("A", domain="hydraulic")
    return v


def test_fresh_valve_has_no_defect():
    assert _prv().defect_active is False


def test_set_defect_changes_p_set_and_marks_active():
    v = _prv(1.5e7)
    v.handle_command({"action": "set_defect", "p_set": 5e6})
    assert v.p_set == 5e6
    assert v.p_hint == 5e6
    assert v.defect_active is True


def test_clear_defect_restores_p_set():
    v = _prv(1.5e7)
    v.handle_command({"action": "set_defect", "p_set": 5e6})
    v.handle_command({"action": "clear_defect"})
    assert v.p_set == 1.5e7
    assert v.defect_active is False


# ---------------------------------------------------------------------------
# Physics -- real solver (relieving valve, oversupplied outlet: A is held at p_set)
# ---------------------------------------------------------------------------

def _circuit(p_set=2.0e6):
    prv = PressureReducingValve("prv", domain="hydraulic", properties={"p_set": p_set, "relieving": True})
    for port in ("P", "A", "T"):
        prv.add_anchor(port, domain="hydraulic")
    supply = FixedDisplacementPump("supply", domain="hydraulic", properties={"Q": 1e-2})
    supply.add_anchor("P", domain="hydraulic")
    supply.add_anchor("S", domain="hydraulic")
    load = FixedDisplacementPump("load", domain="hydraulic", properties={"Q": 2e-4})
    load.add_anchor("P", domain="hydraulic")
    load.add_anchor("S", domain="hydraulic")
    res = {}
    for name in ("res_supply", "res_tank", "res_load"):
        res[name] = Reservoir(name, domain="hydraulic", properties={"pressure": 0.0})
        res[name].add_anchor("T", domain="hydraulic")
    conns = [
        Connection(supply.get_anchor("P"), prv.get_anchor("P")),
        Connection(supply.get_anchor("S"), res["res_supply"].get_anchor("T")),
        Connection(prv.get_anchor("T"), res["res_tank"].get_anchor("T")),
        Connection(prv.get_anchor("A"), load.get_anchor("S")),
        Connection(load.get_anchor("P"), res["res_load"].get_anchor("T")),
    ]
    nodes = {"prv": prv, "supply": supply, "load": load, **res}
    return SimulationEngine(nodes, {c.id: c for c in conns}), prv


def test_outlet_pressure_follows_healthy_p_set():
    engine, prv = _circuit(2.0e6)
    engine.run_until_stable(dt=1.0)
    assert prv.get_anchor("A").pressure == pytest.approx(2.0e6, rel=0.1)


@pytest.mark.parametrize("factor", [0.5, 1.5])
def test_defect_applied_mid_run_converges_to_new_p_set(factor):
    """p_hint feeds ScaleManager.build_context on every hydraulic round,
    so a p_set changed between steps rescales the next solve."""
    engine, prv = _circuit(2.0e6)
    engine.run_until_stable(dt=1.0)

    prv.handle_command({"action": "set_defect", "p_set": 2.0e6 * factor})
    engine.run_until_stable(dt=1.0)
    assert prv.get_anchor("A").pressure == pytest.approx(2.0e6 * factor, rel=0.1)
    assert prv.get_anchor("A").flow == pytest.approx(-2e-4, rel=1e-2)

    prv.handle_command({"action": "clear_defect"})
    engine.run_until_stable(dt=1.0)
    assert prv.get_anchor("A").pressure == pytest.approx(2.0e6, rel=0.1)


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------

def _form_label_texts(dialog):
    from PyQt6.QtWidgets import QFormLayout
    labels = []
    for i in range(dialog._form_layout.rowCount()):
        item = dialog._form_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
        if item and item.widget():
            labels.append(item.widget().text())
    return labels


def test_item_defect_fields_one_spec_in_hydraulic():
    item = PressureReducingValveItem(domain="hydraulic")
    specs = item.defect_fields()
    assert [s.key for s in specs] == ["p_set"]
    assert specs[0].kind == "number"
    assert specs[0].min_value == 0
    assert specs[0].label == "Setpoint pressure (Pa)"


def test_item_defect_fields_empty_outside_hydraulic():
    assert PressureReducingValveItem(domain="pneumatic").defect_fields() == []
    assert PressureReducingValveItem(domain="pneumatic").build_defect_dialog() is None


def test_item_dialog_prefilled_from_properties_before_sync():
    item = PressureReducingValveItem(domain="hydraulic")
    item.properties["p_set"] = 2.5e7
    dialog = item.build_defect_dialog()
    assert float(dialog.defect_widget("p_set").text()) == 2.5e7


def test_item_dialog_prefilled_from_live_domain_node():
    item = PressureReducingValveItem(domain="hydraulic")
    item.properties["p_set"] = 1.5e7
    node = _prv(1.5e7)
    item.command.connect(lambda nid, payload: node.handle_command(payload))
    item.update_from_domain(node)
    node.handle_command({"action": "set_defect", "p_set": 4e6})
    dialog = item.build_defect_dialog()
    assert float(dialog.defect_widget("p_set").text()) == 4e6


def test_item_apply_defect_emits_set_defect_float():
    item = PressureReducingValveItem(domain="hydraulic")
    item.properties["p_set"] = 1.5e7
    dialog = item.build_defect_dialog()
    dialog.defect_widget("p_set").setText("5e6")
    received = []
    item.command.connect(lambda nid, payload: received.append(payload))
    item.apply_defect_from_dialog(dialog)
    assert received == [{"action": "set_defect", "p_set": 5e6}]


def test_item_defect_dialog_label_translates_to_pt_br():
    item = PressureReducingValveItem(domain="hydraulic")
    item.properties["p_set"] = 1.5e7
    language_manager.apply_language(app, "pt_BR")
    try:
        dialog = item.build_defect_dialog()
        try:
            assert "Pressão de ajuste (Pa)" in _form_label_texts(dialog)
        finally:
            dialog.close()
    finally:
        language_manager.apply_language(app, "en")
