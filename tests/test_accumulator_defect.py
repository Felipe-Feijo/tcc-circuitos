import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from main_window.language import language_manager
from tests.defect_test_helpers import form_label_texts
from graphics.items.base.nodes.accumulator import Accumulator as AccumulatorItem
from simulation.connections import Connection
from simulation.nodes.accumulator import Accumulator
from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
from simulation.nodes.reservoir import Reservoir
from simulation.simulation_engine import SimulationEngine

V0 = 1e-3
P0 = 3e6


def _acc(p0=P0):
    a = Accumulator("acc", domain="hydraulic", properties={"V0": V0, "P0": p0})
    a.add_anchor("P", domain="hydraulic")
    return a


def test_fresh_accumulator_has_no_defect():
    assert _acc().defect_active is False


def test_set_defect_lowers_p0_and_gas_pressure_keeps_vf():
    a = _acc()
    a.Vf = 0.4e-3
    healthy = a._p_gas(a.Vf)
    a.handle_command({"action": "set_defect", "P0": P0 * 0.3})
    assert a.P0 == pytest.approx(P0 * 0.3)
    assert a.defect_active is True
    assert a.Vf == 0.4e-3
    assert a._p_gas(a.Vf) == pytest.approx(healthy * 0.3)
    assert a.p_hint == pytest.approx(healthy * 0.3)


def test_clear_defect_restores_p0_and_keeps_vf():
    a = _acc()
    a.Vf = 0.4e-3
    a.handle_command({"action": "set_defect", "P0": P0 * 0.3})
    a.handle_command({"action": "clear_defect"})
    assert a.P0 == P0
    assert a.Vf == 0.4e-3
    assert a.defect_active is False


def _circuit(q=1e-5):
    acc = _acc()
    pump = FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": q})
    pump.add_anchor("P", domain="hydraulic")
    pump.add_anchor("S", domain="hydraulic")
    res = Reservoir("res", domain="hydraulic", properties={"pressure": 0.0})
    res.add_anchor("T", domain="hydraulic")
    conns = [
        Connection(pump.get_anchor("S"), res.get_anchor("T")),
        Connection(pump.get_anchor("P"), acc.get_anchor("P")),
    ]
    nodes = {"pump": pump, "res": res, "acc": acc}
    return SimulationEngine(nodes, {c.id: c for c in conns}), acc


def test_lost_precharge_mid_run_converges_to_new_gas_pressure():
    """P0 drops sharply while fluid is stored; p_hint feeds the scale
    rebuilt every hydraulic round, so the next solve follows P_gas(Vf)."""
    engine, acc = _circuit()
    for _ in range(5):
        engine.run_until_stable(dt=1.0)
    assert acc.Vf > 0.0

    vf_before = acc.Vf
    healthy_p = acc._p_gas(vf_before)
    acc.handle_command({"action": "set_defect", "P0": P0 * 0.3})
    assert acc.Vf == vf_before
    engine.run_until_stable(dt=1.0)
    assert acc.get_anchor("P").pressure == pytest.approx(
        acc._p_gas(vf_before), rel=0.02
    )
    assert acc.get_anchor("P").pressure < 0.5 * healthy_p

    acc.handle_command({"action": "clear_defect"})
    engine.run_until_stable(dt=1.0)
    assert acc.get_anchor("P").pressure == pytest.approx(
        acc._p_gas(acc.Vf), rel=0.05
    )
    assert acc.get_anchor("P").pressure > healthy_p * 0.9


def test_item_defect_fields_one_spec_in_hydraulic():
    specs = AccumulatorItem(domain="hydraulic").defect_fields()
    assert [s.key for s in specs] == ["P0"]
    assert specs[0].kind == "number"
    assert specs[0].min_value == 0
    assert specs[0].label == "Precharge pressure P0 (Pa)"
    assert specs[0].placeholder == "ex: 3e6"


def test_item_dialog_prefilled_from_properties_before_sync():
    item = AccumulatorItem(domain="hydraulic")
    item.properties["P0"] = 2e6
    dialog = item.build_defect_dialog()
    assert float(dialog.defect_widget("P0").text()) == 2e6


def test_item_dialog_prefilled_from_live_domain_node():
    item = AccumulatorItem(domain="hydraulic")
    item.properties["P0"] = P0
    node = _acc()
    item.command.connect(lambda nid, payload: node.handle_command(payload))
    item.update_from_domain(node)
    node.handle_command({"action": "set_defect", "P0": 1e6})
    dialog = item.build_defect_dialog()
    assert float(dialog.defect_widget("P0").text()) == 1e6


def test_item_apply_defect_emits_set_defect_float():
    item = AccumulatorItem(domain="hydraulic")
    item.properties["P0"] = P0
    dialog = item.build_defect_dialog()
    dialog.defect_widget("P0").setText("1e6")
    received = []
    item.command.connect(lambda nid, payload: received.append(payload))
    item.apply_defect_from_dialog(dialog)
    assert received == [{"action": "set_defect", "P0": 1e6}]


def test_item_defect_dialog_label_translates_to_pt_br():
    item = AccumulatorItem(domain="hydraulic")
    item.properties["P0"] = P0
    language_manager.apply_language(app, "pt_BR")
    try:
        dialog = item.build_defect_dialog()
        try:
            assert "Pressão de pré-carga P0 (Pa)" in form_label_texts(dialog)
        finally:
            dialog.close()
    finally:
        language_manager.apply_language(app, "en")
