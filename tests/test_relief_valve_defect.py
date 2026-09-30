import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from main_window.language import language_manager
from graphics.items.base.nodes.relief_valve import ReliefValve as ReliefValveItem
from simulation.connections import Connection
from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
from simulation.nodes.relief_valve import ReliefValve
from simulation.nodes.reservoir import Reservoir
from simulation.simulation_engine import SimulationEngine


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------

def _valve(p_set=1.5e7):
    v = ReliefValve("rv", domain="hydraulic", properties={"p_set": p_set})
    v.add_anchor("P", domain="hydraulic")
    v.add_anchor("T", domain="hydraulic")
    return v


def test_fresh_valve_has_no_defect():
    assert _valve().defect_active is False


def test_set_defect_changes_p_set_and_marks_active():
    v = _valve(1.5e7)
    v.handle_command({"action": "set_defect", "p_set": 5e6})
    assert v.p_set == 5e6
    assert v.p_hint == 5e6
    assert v.defect_active is True


def test_clear_defect_restores_p_set():
    v = _valve(1.5e7)
    v.handle_command({"action": "set_defect", "p_set": 5e6})
    v.handle_command({"action": "clear_defect"})
    assert v.p_set == 1.5e7
    assert v.defect_active is False


# ---------------------------------------------------------------------------
# Physics -- real solver
# ---------------------------------------------------------------------------

def _circuit(p_set=1.5e7, q=1e-3):
    rv = _valve(p_set)
    pump = FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": q})
    pump.add_anchor("P", domain="hydraulic")
    pump.add_anchor("S", domain="hydraulic")
    res_s = Reservoir("res_s", domain="hydraulic", properties={"pressure": 0.0})
    res_s.add_anchor("T", domain="hydraulic")
    res_t = Reservoir("res_t", domain="hydraulic", properties={"pressure": 0.0})
    res_t.add_anchor("T", domain="hydraulic")
    conns = [
        Connection(pump.get_anchor("P"), rv.get_anchor("P")),
        Connection(pump.get_anchor("S"), res_s.get_anchor("T")),
        Connection(rv.get_anchor("T"), res_t.get_anchor("T")),
    ]
    nodes = {"rv": rv, "pump": pump, "res_s": res_s, "res_t": res_t}
    engine = SimulationEngine(nodes, {c.id: c for c in conns})
    return engine, rv


def test_line_pressure_follows_healthy_p_set():
    engine, rv = _circuit(1.5e7)
    engine.run_until_stable(dt=1.0)
    assert rv.get_anchor("P").pressure == pytest.approx(1.5e7, rel=0.05)


@pytest.mark.parametrize("factor", [0.5, 1.5])
def test_defect_applied_mid_run_converges_to_new_p_set(factor):
    """p_hint feeds ScaleManager.build_context on every hydraulic round,
    so a p_set changed between steps rescales the next solve."""
    engine, rv = _circuit(1.5e7)
    engine.run_until_stable(dt=1.0)

    rv.handle_command({"action": "set_defect", "p_set": 1.5e7 * factor})
    engine.run_until_stable(dt=1.0)
    assert rv.get_anchor("P").pressure == pytest.approx(1.5e7 * factor, rel=0.05)
    assert rv.get_anchor("T").flow == pytest.approx(-1e-3, rel=0.05)

    rv.handle_command({"action": "clear_defect"})
    engine.run_until_stable(dt=1.0)
    assert rv.get_anchor("P").pressure == pytest.approx(1.5e7, rel=0.05)


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
    item = ReliefValveItem(domain="hydraulic")
    specs = item.defect_fields()
    assert [s.key for s in specs] == ["p_set"]
    assert specs[0].kind == "number"
    assert specs[0].min_value == 0
    assert specs[0].label == "Cracking pressure (Pa)"


def test_item_defect_fields_empty_outside_hydraulic():
    assert ReliefValveItem(domain="pneumatic").defect_fields() == []
    assert ReliefValveItem(domain="pneumatic").build_defect_dialog() is None


def test_item_dialog_prefilled_from_properties_before_sync():
    item = ReliefValveItem(domain="hydraulic")
    item.properties["p_set"] = 2.5e7
    dialog = item.build_defect_dialog()
    assert float(dialog.defect_widget("p_set").text()) == 2.5e7


def test_item_dialog_prefilled_from_live_domain_node():
    item = ReliefValveItem(domain="hydraulic")
    item.properties["p_set"] = 1.5e7
    node = _valve(1.5e7)
    item.command.connect(lambda nid, payload: node.handle_command(payload))
    item.update_from_domain(node)
    node.handle_command({"action": "set_defect", "p_set": 4e6})
    dialog = item.build_defect_dialog()
    assert float(dialog.defect_widget("p_set").text()) == 4e6


def test_item_apply_defect_emits_set_defect_float():
    item = ReliefValveItem(domain="hydraulic")
    item.properties["p_set"] = 1.5e7
    dialog = item.build_defect_dialog()
    dialog.defect_widget("p_set").setText("5e6")
    received = []
    item.command.connect(lambda nid, payload: received.append(payload))
    item.apply_defect_from_dialog(dialog)
    assert received == [{"action": "set_defect", "p_set": 5e6}]


def test_item_defect_dialog_label_translates_to_pt_br():
    item = ReliefValveItem(domain="hydraulic")
    item.properties["p_set"] = 1.5e7
    language_manager.apply_language(app, "pt_BR")
    try:
        dialog = item.build_defect_dialog()
        try:
            assert "Pressão de abertura (Pa)" in _form_label_texts(dialog)
        finally:
            dialog.close()
    finally:
        language_manager.apply_language(app, "en")
