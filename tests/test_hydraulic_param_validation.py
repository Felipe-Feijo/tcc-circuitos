"""Range validation for hydraulic parameters where zero does NOT mean
"closed", shared by __init__, set_defect and the properties/defect
dialogs.

Rules: CentrifugalPump Q_max > 0, H_shutoff >= 0; cylinders bore > 0,
stroke > 0, 0 <= rod_diameter < bore, spring_k >= 0; Accumulator V0 > 0,
P0 > 0; FixedDisplacementMotor D > 0; FixedDisplacementPump Q > 0;
relief/PRV/pilot-operated relief p_set > 0 (and p_vent > 0); k >= 0.

An invalid defect is rejected (rolled back, logged, kept in
defect_error) instead of reaching the solver.
"""

import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from main_window.language import language_manager
from graphics.items.base.nodes.accumulator import Accumulator as AccumulatorItem
from graphics.items.base.nodes.cylinder.double_acting_cylinder import (
    DoubleActingCylinder as DoubleItem,
)
from graphics.items.base.nodes.cylinder.single_acting_cylinder import (
    SingleActingCylinder as SingleItem,
)
from graphics.items.base.nodes.fixed_displacement_motor import (
    FixedDisplacementMotor as MotorItem,
)
from graphics.items.base.nodes.pilot_operated_relief_valve import (
    PilotOperatedReliefValve as PorItem,
)
from graphics.items.base.nodes.pressure_reducing_valve import (
    PressureReducingValve as PrvItem,
)
from graphics.items.base.nodes.pumps.centrifugal_pump import CentrifugalPump as CentrifugalItem
from graphics.items.base.nodes.pumps.fixed_displacement_pump import (
    FixedDisplacementPump as PumpItem,
)
from graphics.items.base.nodes.relief_valve import ReliefValve as ReliefItem
from simulation.connections import Connection
from simulation.graph_builder import GraphBuilder
from simulation.nodes.accumulator import Accumulator
from simulation.nodes.check_valve.throttle_check_valve import ThrottleCheckValve
from simulation.nodes.cylinder.double_acting_cylinder import DoubleActingCylinder
from simulation.nodes.cylinder.single_acting_cylinder import SingleActingCylinder
from simulation.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways
from simulation.nodes.fixed_displacement_motor import FixedDisplacementMotor
from simulation.nodes.pilot_operated_relief_valve import PilotOperatedReliefValve
from simulation.nodes.pressure_reducing_valve import PressureReducingValve
from simulation.nodes.pumps.centrifugal_pump import CentrifugalPump
from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
from simulation.nodes.relief_valve import ReliefValve
from simulation.nodes.reservoir import Reservoir
from simulation.nodes.throttle_valve import ThrottleValve
from simulation.simulation_engine import SimulationEngine

CENTRIFUGAL = {"H_shutoff": 2e6, "Q_max": 8e-4}
DOUBLE = {"bore": 0.05, "rod_diameter": 0.02, "stroke": 0.2}
SINGLE = {"bore": 0.05, "stroke": 0.2, "spring_k": 5000.0}
ACCUMULATOR = {"V0": 1e-3, "P0": 3e6}
MOTOR = {"D": 1.5e-6, "control_mode": "torque", "T_load": 10.0}


def _make(cls, base, **override):
    return cls("n", domain="hydraulic", properties={**base, **override})


# ---------------------------------------------------------------------------
# __init__: rejected with a message naming the property
# ---------------------------------------------------------------------------

INVALID_PROPERTIES = [
    (CentrifugalPump, CENTRIFUGAL, {"Q_max": 0.0}, r"'Q_max' must be > 0"),
    (CentrifugalPump, CENTRIFUGAL, {"Q_max": -1e-4}, r"'Q_max' must be > 0"),
    (CentrifugalPump, CENTRIFUGAL, {"H_shutoff": -1.0}, r"'H_shutoff' must be >= 0"),
    (DoubleActingCylinder, DOUBLE, {"bore": 0.0, "rod_diameter": 0.0}, r"'bore' must be > 0"),
    (DoubleActingCylinder, DOUBLE, {"rod_diameter": 0.05}, r"'rod_diameter' must be < bore"),
    (DoubleActingCylinder, DOUBLE, {"rod_diameter": 0.06}, r"'rod_diameter' must be < bore"),
    (DoubleActingCylinder, DOUBLE, {"rod_diameter": -0.01}, r"'rod_diameter' must be >= 0"),
    (DoubleActingCylinder, DOUBLE, {"stroke": 0.0}, r"'stroke' must be > 0"),
    (SingleActingCylinder, SINGLE, {"bore": 0.0}, r"'bore' must be > 0"),
    (SingleActingCylinder, SINGLE, {"stroke": 0.0}, r"'stroke' must be > 0"),
    (SingleActingCylinder, SINGLE, {"spring_k": -1.0}, r"'spring_k' must be >= 0"),
    (Accumulator, ACCUMULATOR, {"V0": 0.0}, r"'V0' must be > 0"),
    (Accumulator, ACCUMULATOR, {"P0": 0.0}, r"'P0' must be > 0"),
    (Accumulator, ACCUMULATOR, {"P0": -1e5}, r"'P0' must be > 0"),
    (FixedDisplacementMotor, MOTOR, {"D": 0.0}, r"'D' must be > 0"),
    (FixedDisplacementMotor, MOTOR, {"D": -1e-6}, r"'D' must be > 0"),
    (FixedDisplacementPump, {"Q": 1e-4}, {"Q": 0.0}, r"'Q' must be > 0"),
    (ReliefValve, {"p_set": 1e7}, {"p_set": 0.0}, r"'p_set' must be > 0"),
    (PressureReducingValve, {"p_set": 1e7}, {"p_set": 0.0}, r"'p_set' must be > 0"),
    (PilotOperatedReliefValve, {"p_set": 1e7}, {"p_set": 0.0}, r"'p_set' must be > 0"),
    (PilotOperatedReliefValve, {"p_set": 1e7}, {"p_vent": 0.0}, r"'p_vent' must be > 0"),
]


@pytest.mark.parametrize("cls, base, override, match", [
    pytest.param(*case, id=f"{case[0].__name__}-{case[2]}") for case in INVALID_PROPERTIES
])
def test_invalid_property_raises_value_error(cls, base, override, match):
    with pytest.raises(ValueError, match=match):
        _make(cls, base, **override)


@pytest.mark.parametrize("cls, base, override", [
    pytest.param(CentrifugalPump, CENTRIFUGAL, {"H_shutoff": 0.0}, id="CentrifugalPump-H_shutoff=0"),
    pytest.param(DoubleActingCylinder, DOUBLE, {"rod_diameter": 0.0}, id="DoubleActingCylinder-rod=0"),
    pytest.param(SingleActingCylinder, SINGLE, {"spring_k": 0.0}, id="SingleActingCylinder-spring_k=0"),
])
def test_boundary_value_is_accepted(cls, base, override):
    _make(cls, base, **override)


def test_message_names_class_and_id():
    with pytest.raises(ValueError, match=r"^CentrifugalPump 'n': property 'Q_max' must be > 0, got 0.0\.$"):
        _make(CentrifugalPump, CENTRIFUGAL, Q_max=0.0)


def test_nan_is_rejected():
    with pytest.raises(ValueError, match=r"'Q_max' must be > 0"):
        _make(CentrifugalPump, CENTRIFUGAL, Q_max=float("nan"))


def test_pneumatic_cylinder_skips_hydraulic_geometry():
    DoubleActingCylinder("n", domain="pneumatic", properties={})


def test_graph_builder_reports_invalid_property_before_simulation():
    item = CentrifugalItem(domain="hydraulic")
    item.properties.update(H_shutoff=2e6, Q_max=0.0)
    builder = GraphBuilder()
    assert builder.add_node_from_item(item) is None
    with pytest.raises(ValueError, match=r"'Q_max' must be > 0"):
        builder.raise_if_errors()


# ---------------------------------------------------------------------------
# set_defect: invalid values rejected, node unchanged
# ---------------------------------------------------------------------------

def _throttle(k=1e-7):
    return ThrottleValve("tv", domain="hydraulic", properties={"k": k})


INVALID_DEFECTS = [
    (lambda: _throttle(), {"k": -1e-7}, "k", 1e-7, r"'k' must be >= 0"),
    (lambda: ThrottleCheckValve("tcv", domain="hydraulic", properties={"k": 1e-7}),
     {"k": -1e-7}, "k", 1e-7, r"'k' must be >= 0"),
    (lambda: Valve_4_2_Ways("v", domain="hydraulic", properties={"k": 1e-7}),
     {"k": -1e-7, "stuck": True}, "k", 1e-7, r"'k' must be >= 0"),
    (lambda: _make(CentrifugalPump, CENTRIFUGAL), {"Q_max": 0.0}, "Q_max", 8e-4, r"'Q_max' must be > 0"),
    (lambda: _make(CentrifugalPump, CENTRIFUGAL), {"H_shutoff": -1.0}, "H_shutoff", 2e6, r"'H_shutoff' must be >= 0"),
    (lambda: _make(Accumulator, ACCUMULATOR), {"P0": 0.0}, "P0", 3e6, r"'P0' must be > 0"),
    (lambda: _make(FixedDisplacementPump, {"Q": 1e-4}), {"Q": 0.0}, "Q", 1e-4, r"'Q' must be > 0"),
    (lambda: _make(ReliefValve, {"p_set": 1e7}), {"p_set": 0.0}, "p_set", 1e7, r"'p_set' must be > 0"),
    (lambda: _make(PressureReducingValve, {"p_set": 1e7}), {"p_set": -1.0}, "p_set", 1e7, r"'p_set' must be > 0"),
    (lambda: _make(PilotOperatedReliefValve, {"p_set": 1e7}), {"p_set": 0.0}, "p_set", 1e7, r"'p_set' must be > 0"),
    (lambda: _throttle(), {"k": "abc"}, "k", 1e-7, r"could not convert"),
]


@pytest.mark.parametrize("make, payload, key, healthy, match", [
    pytest.param(*case, id=f"{i}-{list(case[1])}") for i, case in enumerate(INVALID_DEFECTS)
])
def test_invalid_defect_is_rejected_without_exception(make, payload, key, healthy, match, caplog):
    node = make()
    with caplog.at_level("WARNING"):
        node.handle_command({"action": "set_defect", **payload, "note": "bad"})
    assert node.defect_value(key) == healthy
    assert node.defect_active is False
    assert node.defect_note == ""
    assert node.defect_error
    assert re.search(match, node.defect_error)
    assert "defect rejected" in caplog.text


def test_rejected_command_rolls_back_every_field_it_touched():
    """k and stuck arrive together; the bad k must not leave stuck applied."""
    v = Valve_4_2_Ways("v", domain="hydraulic", properties={"k": 1e-7})
    v.handle_command({"action": "set_defect", "k": -1.0, "stuck": True})
    assert v.stuck_defect is False
    assert v.k == 1e-7


def test_rejected_defect_keeps_previous_defect_and_clear_still_restores():
    tv = _throttle()
    tv.handle_command({"action": "set_defect", "k": 3e-8})
    tv.handle_command({"action": "set_defect", "k": -1.0})
    assert tv.k == 3e-8
    assert tv.defect_active is True
    tv.handle_command({"action": "clear_defect"})
    assert tv.k == 1e-7
    assert tv.defect_active is False
    assert tv.defect_error == ""


def test_accepted_defect_clears_previous_error():
    tv = _throttle()
    tv.handle_command({"action": "set_defect", "k": -1.0})
    assert tv.defect_error
    tv.handle_command({"action": "set_defect", "k": 0.0})
    assert tv.defect_error == ""
    assert tv.k == 0.0


@pytest.mark.parametrize("payload", [
    pytest.param({"H_shutoff": 0.0}, id="H_shutoff=0"),
    pytest.param({"Q_max": 4e-4}, id="Q_max-halved"),
])
def test_valid_centrifugal_defect_still_applies(payload):
    pump = _make(CentrifugalPump, CENTRIFUGAL)
    pump.handle_command({"action": "set_defect", **payload})
    assert pump.defect_active is True
    assert pump.defect_error == ""


# ---------------------------------------------------------------------------
# Simulation keeps running after a rejected defect
# ---------------------------------------------------------------------------

def _pump_throttle_circuit(k=1e-7, q=1e-4):
    tv = _throttle(k)
    tv.add_anchor("X", domain="hydraulic")
    tv.add_anchor("Y", domain="hydraulic")
    pump = FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": q})
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
    return SimulationEngine(nodes, {c.id: c for c in conns}), tv, pump


@pytest.mark.parametrize("target, payload", [
    pytest.param("tv", {"k": -1e-7}, id="throttle-k<0"),
    pytest.param("pump", {"Q": 0.0}, id="pump-Q=0"),
])
def test_simulation_continues_unchanged_after_rejected_defect(target, payload):
    engine, tv, pump = _pump_throttle_circuit()
    engine.run_until_stable(dt=1.0)
    drop = tv.get_anchor("X").pressure - tv.get_anchor("Y").pressure

    {"tv": tv, "pump": pump}[target].handle_command({"action": "set_defect", **payload})
    engine.run_until_stable(dt=1.0)
    engine.run_until_stable(dt=1.0)
    new_drop = tv.get_anchor("X").pressure - tv.get_anchor("Y").pressure
    assert new_drop == pytest.approx(drop, rel=0.02)
    assert tv.get_anchor("X").flow == pytest.approx(1e-4, rel=0.02)


# ---------------------------------------------------------------------------
# Dialogs: OK disabled and the reason shown
# ---------------------------------------------------------------------------

def _set(dialog, field, text):
    field.setText(text)
    dialog._refresh_ok_button()


def _assert_rejected(dialog, message):
    assert dialog._ok_btn.isEnabled() is False
    assert dialog._error_label.isVisibleTo(dialog)
    assert dialog._error_label.text() == message


def _assert_accepted(dialog):
    assert dialog._ok_btn.isEnabled() is True
    assert dialog._error_label.isVisibleTo(dialog) is False


@pytest.mark.parametrize("item_cls, props, field_attr, bad, label, rule", [
    pytest.param(CentrifugalItem, CENTRIFUGAL, "_field_qmax", "0", "Maximum flow (m³/s)", "must be greater than 0", id="Q_max"),
    pytest.param(CentrifugalItem, CENTRIFUGAL, "_field_h", "-1", "Shutoff pressure H (Pa)", "must be at least 0", id="H_shutoff"),
    pytest.param(PumpItem, {"Q": 1e-4}, "_field_Q", "0", "Flow rate (m³/s)", "must be greater than 0", id="pump-Q"),
    pytest.param(AccumulatorItem, ACCUMULATOR, "_field_v0", "0", "Total volume V0 (m³)", "must be greater than 0", id="V0"),
    pytest.param(AccumulatorItem, ACCUMULATOR, "_field_p0", "0", "Precharge pressure P0 (Pa)", "must be greater than 0", id="P0"),
    pytest.param(ReliefItem, {"p_set": 1e7}, "_field_p_set", "0", "Cracking pressure (Pa)", "must be greater than 0", id="relief-p_set"),
    pytest.param(PrvItem, {"p_set": 1e7}, "_field_p_set", "0", "Setpoint pressure (Pa)", "must be greater than 0", id="prv-p_set"),
    pytest.param(PorItem, {"p_set": 1e7}, "_field_p_set", "0", "Pilot setting (Pa)", "must be greater than 0", id="por-p_set"),
    pytest.param(PorItem, {"p_set": 1e7}, "_field_p_vent", "0", "Main-stage spring (Pa)", "must be greater than 0", id="por-p_vent"),
    pytest.param(MotorItem, {"D": 1.5e-6, "T_load": 10.0}, "_field_d", "0", "Displacement D (m³/rad)", "must be greater than 0", id="motor-D"),
    pytest.param(DoubleItem, DOUBLE, "_field_bore", "0", "Bore diameter (m)", "must be greater than 0", id="double-bore"),
    pytest.param(DoubleItem, DOUBLE, "_field_stroke", "0", "Stroke (m)", "must be greater than 0", id="double-stroke"),
    pytest.param(DoubleItem, DOUBLE, "_field_rod", "-0.01", "Rod diameter (m)", "must be at least 0", id="double-rod<0"),
    pytest.param(SingleItem, SINGLE, "_field_bore", "0", "Bore diameter (m)", "must be greater than 0", id="single-bore"),
    pytest.param(SingleItem, SINGLE, "_field_stroke", "0", "Stroke (m)", "must be greater than 0", id="single-stroke"),
    pytest.param(SingleItem, SINGLE, "_field_spring_k", "-1", "Spring constant (N/m)", "must be at least 0", id="single-spring_k"),
])
def test_properties_dialog_rejects_with_message(item_cls, props, field_attr, bad, label, rule):
    item = item_cls(domain="hydraulic")
    item.properties.update(props)
    dialog = item.build_properties_dialog()
    try:
        field = getattr(dialog, field_attr)
        _assert_accepted(dialog)
        _set(dialog, field, bad)
        _assert_rejected(dialog, f"{label}: {rule}")
        assert field.toolTip() == rule
        _set(dialog, field, "1")
        assert field.toolTip() == ""
    finally:
        dialog.close()


@pytest.mark.parametrize("rod", ["0.05", "0.06"])
def test_double_acting_dialog_rejects_rod_not_smaller_than_bore(rod):
    item = DoubleItem(domain="hydraulic")
    item.properties.update(DOUBLE)
    dialog = item.build_properties_dialog()
    try:
        _set(dialog, dialog._field_rod, rod)
        _assert_rejected(dialog, "Rod diameter must be smaller than the bore diameter.")
        _set(dialog, dialog._field_bore, "0.08")
        _assert_accepted(dialog)
    finally:
        dialog.close()


def test_double_acting_dialog_accepts_rod_zero():
    item = DoubleItem(domain="hydraulic")
    item.properties.update(DOUBLE)
    dialog = item.build_properties_dialog()
    try:
        _set(dialog, dialog._field_rod, "0")
        _assert_accepted(dialog)
    finally:
        dialog.close()


def test_centrifugal_dialogs_accept_h_shutoff_zero():
    item = CentrifugalItem(domain="hydraulic")
    item.properties.update(CENTRIFUGAL)
    dialog = item.build_properties_dialog()
    defect = item.build_defect_dialog()
    try:
        _set(dialog, dialog._field_h, "0")
        _assert_accepted(dialog)
        _set(defect, defect.defect_widget("H_shutoff"), "0")
        _assert_accepted(defect)
    finally:
        dialog.close()
        defect.close()


def test_defect_dialog_rejects_with_message():
    item = PumpItem(domain="hydraulic")
    item.properties["Q"] = 1e-4
    dialog = item.build_defect_dialog()
    try:
        _set(dialog, dialog.defect_widget("Q"), "0")
        _assert_rejected(dialog, "Flow rate (m³/s): must be greater than 0")
    finally:
        dialog.close()


def test_empty_required_field_disables_ok_without_message():
    item = CentrifugalItem(domain="hydraulic")
    dialog = item.build_properties_dialog()
    try:
        assert dialog._ok_btn.isEnabled() is False
        assert dialog._error_label.isVisibleTo(dialog) is False
    finally:
        dialog.close()


def test_messages_are_translated_to_pt_br():
    language_manager.apply_language(app, "pt_BR")
    try:
        item = DoubleItem(domain="hydraulic")
        item.properties.update(DOUBLE)
        dialog = item.build_properties_dialog()
        try:
            _set(dialog, dialog._field_stroke, "0")
            assert dialog._error_label.text().endswith(": deve ser maior que 0")
            _set(dialog, dialog._field_stroke, "0.2")
            _set(dialog, dialog._field_rod, "-1")
            assert dialog._error_label.text().endswith(": deve ser no mínimo 0")
            _set(dialog, dialog._field_rod, "abc")
            assert dialog._error_label.text().endswith(": não é um número válido")
            _set(dialog, dialog._field_rod, "0.06")
            assert dialog._error_label.text() == (
                "O diâmetro da haste deve ser menor que o diâmetro do êmbolo."
            )
        finally:
            dialog.close()
    finally:
        language_manager.apply_language(app, "en")
