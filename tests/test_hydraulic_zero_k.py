"""k = 0 as an exact block for every node using dP = sgn(Q)*(Q/k)^2:
ThrottleValve, ThrottleCheckValve and the hydraulic directional valves.

A tiny k can't stand in for "closed" (the solver stops converging), so
k == 0 drops the orifice from the solve -- same pattern as a closed
Valve_2_2_Ways. Blocking is evaluated from the current k, so a "k"
defect can clog/unclog a valve mid-run.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.check_valve.throttle_check_valve import (
    ThrottleCheckValve as ThrottleCheckValveItem,
)
from graphics.items.base.nodes.directional_valve.valve_4_2_ways import (
    Valve_4_2_Ways as Valve_4_2_WaysItem,
)
from graphics.items.base.nodes.reservoir import Reservoir as ReservoirItem
from graphics.items.base.nodes.throttle_valve import ThrottleValve as ThrottleValveItem
from simulation.connections import Connection
from simulation.graph_builder import GraphBuilder
from simulation.nodes.check_valve.throttle_check_valve import ThrottleCheckValve
from simulation.nodes.directional_valve.valve_2_2_ways import Valve_2_2_Ways
from simulation.nodes.directional_valve.valve_3_2_ways import Valve_3_2_Ways
from simulation.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways
from simulation.nodes.directional_valve.valve_4_3_ways import Valve_4_3_Ways
from simulation.nodes.directional_valve.valve_5_2_ways import Valve_5_2_Ways
from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
from simulation.nodes.relief_valve import ReliefValve
from simulation.nodes.reservoir import Reservoir
from simulation.nodes.throttle_valve import ThrottleValve
from simulation.simulation_engine import SimulationEngine

K = 1e-7
Q = 1e-4
P_SET = 1.5e7
HEALTHY_DROP = (Q / K) ** 2  # 1e6 Pa, well below P_SET

# (class, ports, [(body_state, inlet, outlet), ...]) -- one entry per
# open passage the pump can feed in that position.
DIRECTIONAL = [
    (Valve_2_2_Ways, ("P", "A"), [(1, "P", "A")]),
    (Valve_3_2_Ways, ("P", "A", "R"), [(1, "P", "A"), (0, "A", "R")]),
    (Valve_4_2_Ways, ("P", "A", "B", "R"), [(0, "P", "A"), (1, "P", "B")]),
    (Valve_4_3_Ways, ("P", "A", "B", "R"), [(0, "P", "A"), (2, "P", "B")]),
    (Valve_5_2_Ways, ("P", "A", "B", "R1", "R2"), [(1, "P", "A"), (0, "P", "B")]),
]
DIRECTIONAL_CASES = [
    pytest.param(cls, ports, state, inlet, outlet,
                 id=f"{cls.__name__}-state{state}-{inlet}{outlet}")
    for cls, ports, positions in DIRECTIONAL
    for state, inlet, outlet in positions
]
DIRECTIONAL_CLASSES = [pytest.param(cls, id=cls.__name__) for cls, _, _ in DIRECTIONAL]


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _throttle(k=K):
    v = ThrottleValve("tv", domain="hydraulic", properties={"k": k})
    v.add_anchor("X", domain="hydraulic")
    v.add_anchor("Y", domain="hydraulic")
    return v


def _throttle_check(k=K):
    v = ThrottleCheckValve("tcv", domain="hydraulic", properties={"k": k})
    v.add_anchor("X", domain="hydraulic")
    v.add_anchor("Y", domain="hydraulic")
    return v


def _directional(cls, ports, body_state, k=K):
    v = cls("dv", domain="hydraulic", properties={"k": k})
    for port in ports:
        v.add_anchor(port, domain="hydraulic")
    v.body_state = body_state
    if v.THREE_POSITION:
        # update() recomputes the body from the bits: 00 -> center.
        v.bits = {"left": int(body_state == 2), "right": int(body_state == 0)}
    return v


def _pump_relief_circuit(component, inlet, outlets):
    """Pump + relief on the line feeding `component.inlet`; every port in
    `outlets` goes to its own tank."""
    pump = FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": Q})
    pump.add_anchor("P", domain="hydraulic")
    pump.add_anchor("S", domain="hydraulic")
    rv = ReliefValve("rv", domain="hydraulic", properties={"p_set": P_SET})
    rv.add_anchor("P", domain="hydraulic")
    rv.add_anchor("T", domain="hydraulic")
    nodes = {component.id: component, "pump": pump, "rv": rv}
    conns = [
        Connection(pump.get_anchor("P"), component.get_anchor(inlet)),
        Connection(pump.get_anchor("P"), rv.get_anchor("P")),
    ]
    tanks = [("res_s", pump.get_anchor("S")), ("res_rv", rv.get_anchor("T"))]
    tanks += [(f"res_{port}", component.get_anchor(port)) for port in outlets]
    for name, anchor in tanks:
        res = Reservoir(name, domain="hydraulic", properties={"pressure": 0.0})
        res.add_anchor("T", domain="hydraulic")
        nodes[name] = res
        conns.append(Connection(anchor, res.get_anchor("T")))
    engine = SimulationEngine(nodes, {c.id: c for c in conns})
    return engine, rv


def _directional_circuit(cls, ports, body_state, inlet, k=K):
    valve = _directional(cls, ports, body_state, k=k)
    outlets = [p for p in ports if p != inlet]
    engine, rv = _pump_relief_circuit(valve, inlet, outlets)
    return engine, valve, rv


def _line_pressure(rv):
    return rv.get_anchor("P").pressure


def _assert_healthy(rv, component, inlet):
    assert _line_pressure(rv) == pytest.approx(HEALTHY_DROP, rel=0.02)
    assert component.get_anchor(inlet).flow == pytest.approx(Q, rel=0.02)
    assert abs(rv.get_anchor("P").flow) < Q * 1e-3


def _assert_blocked(rv, component):
    """Every pump flow diverted through the relief, line held at p_set."""
    assert _line_pressure(rv) == pytest.approx(P_SET, rel=0.05)
    assert rv.get_anchor("P").flow == pytest.approx(Q, rel=0.02)
    for anchor in component.anchors.values():
        assert anchor.flow == 0.0


# ---------------------------------------------------------------------------
# ThrottleValve -- hydraulic contract with k = 0
# ---------------------------------------------------------------------------

def test_throttle_valve_k_zero_builds_with_empty_contract():
    v = _throttle(k=0.0)
    assert v.blocked is True
    assert v.variables == []
    assert v.hydraulic_ports() == {}
    assert v.initial_guess == {}
    assert v.equations(np.array([]), {}) == []


def test_throttle_valve_k_zero_accepts_int_zero():
    assert _throttle(k=0).blocked is True


def test_throttle_valve_pump_relief_k_zero_diverts_all_flow_to_relief():
    tv = _throttle(k=0.0)
    engine, rv = _pump_relief_circuit(tv, "X", ["Y"])
    engine.run_until_stable(dt=1.0)
    _assert_blocked(rv, tv)


def test_throttle_valve_defect_k_zero_mid_run_blocks_then_clear_restores():
    tv = _throttle()
    engine, rv = _pump_relief_circuit(tv, "X", ["Y"])
    engine.run_until_stable(dt=1.0)
    _assert_healthy(rv, tv, "X")

    tv.handle_command({"action": "set_defect", "k": 0.0})
    engine.run_until_stable(dt=1.0)
    assert tv.blocked is True
    _assert_blocked(rv, tv)

    tv.handle_command({"action": "clear_defect"})
    engine.run_until_stable(dt=1.0)
    assert tv.blocked is False
    _assert_healthy(rv, tv, "X")


# ---------------------------------------------------------------------------
# ThrottleCheckValve -- k = 0 degenerates into a plain check valve
# ---------------------------------------------------------------------------

def test_throttle_check_valve_k_zero_builds_and_keeps_ports():
    v = _throttle_check(k=0.0)
    assert v.restricted_blocked is True
    assert set(v.hydraulic_ports()) == {"X", "Y"}
    assert v.bounds == {v.flow_var_y: (0.0, None), v.flow_var_x: (None, 0.0)}


def test_throttle_check_valve_k_positive_has_no_bounds():
    assert _throttle_check().bounds == {}


def test_throttle_check_valve_k_zero_free_direction_still_conducts():
    """Pump into Y (favorable): zero pressure drop, full flow -- a check valve."""
    tcv = _throttle_check(k=0.0)
    engine, rv = _pump_relief_circuit(tcv, "Y", ["X"])
    engine.run_until_stable(dt=1.0)
    assert tcv.get_anchor("Y").flow == pytest.approx(Q, rel=0.02)
    assert tcv.get_anchor("X").flow == pytest.approx(-Q, rel=0.02)
    assert abs(tcv.get_anchor("X").pressure - tcv.get_anchor("Y").pressure) < 1e3


def test_throttle_check_valve_k_zero_restricted_direction_is_blocked():
    """Pump into X (restricted): no flow through the valve, relief at p_set."""
    tcv = _throttle_check(k=0.0)
    engine, rv = _pump_relief_circuit(tcv, "X", ["Y"])
    engine.run_until_stable(dt=1.0)
    assert _line_pressure(rv) == pytest.approx(P_SET, rel=0.05)
    assert rv.get_anchor("P").flow == pytest.approx(Q, rel=0.02)
    assert abs(tcv.get_anchor("X").flow) < Q * 1e-3


def test_throttle_check_valve_defect_k_zero_mid_run_blocks_then_clear_restores():
    tcv = _throttle_check()
    engine, rv = _pump_relief_circuit(tcv, "X", ["Y"])
    engine.run_until_stable(dt=1.0)
    _assert_healthy(rv, tcv, "X")

    tcv.handle_command({"action": "set_defect", "k": 0.0})
    engine.run_until_stable(dt=1.0)
    assert tcv.restricted_blocked is True
    assert _line_pressure(rv) == pytest.approx(P_SET, rel=0.05)
    assert abs(tcv.get_anchor("X").flow) < Q * 1e-3

    tcv.handle_command({"action": "clear_defect"})
    engine.run_until_stable(dt=1.0)
    assert tcv.restricted_blocked is False
    _assert_healthy(rv, tcv, "X")


# ---------------------------------------------------------------------------
# Directional valves -- k = 0 blocks every open passage
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls, ports, state, inlet, outlet", DIRECTIONAL_CASES)
def test_directional_k_zero_has_empty_contract(cls, ports, state, inlet, outlet):
    v = _directional(cls, ports, state, k=0.0)
    assert v.hydraulic_blocked is True
    assert v.variables == []
    assert v.hydraulic_ports() == {}
    assert v.initial_guess == {}
    assert v.equations(np.array([]), {}) == []


@pytest.mark.parametrize("cls, ports, state, inlet, outlet", DIRECTIONAL_CASES)
def test_directional_pump_relief_k_zero_diverts_all_flow_to_relief(cls, ports, state, inlet, outlet):
    engine, valve, rv = _directional_circuit(cls, ports, state, inlet, k=0.0)
    engine.run_until_stable(dt=1.0)
    _assert_blocked(rv, valve)


@pytest.mark.parametrize("cls, ports, state, inlet, outlet", DIRECTIONAL_CASES)
def test_directional_defect_k_zero_mid_run_blocks_then_clear_restores(cls, ports, state, inlet, outlet):
    engine, valve, rv = _directional_circuit(cls, ports, state, inlet)
    engine.run_until_stable(dt=1.0)
    _assert_healthy(rv, valve, inlet)

    valve.handle_command({"action": "set_defect", "k": 0.0, "stuck": False})
    engine.run_until_stable(dt=1.0)
    assert valve.hydraulic_blocked is True
    _assert_blocked(rv, valve)

    valve.handle_command({"action": "clear_defect"})
    engine.run_until_stable(dt=1.0)
    assert valve.hydraulic_blocked is False
    _assert_healthy(rv, valve, inlet)
    assert valve.get_anchor(outlet).flow == pytest.approx(-Q, rel=0.02)


def test_pneumatic_directional_is_never_hydraulic_blocked():
    v = Valve_4_2_Ways("v", domain="pneumatic", properties={})
    assert v.hydraulic_blocked is False


# ---------------------------------------------------------------------------
# Regression: k > 0 still follows the orifice equation
# ---------------------------------------------------------------------------

def test_throttle_valve_k_positive_follows_orifice_equation():
    tv = _throttle()
    engine, rv = _pump_relief_circuit(tv, "X", ["Y"])
    engine.run_until_stable(dt=1.0)
    _assert_healthy(rv, tv, "X")
    assert tv.get_anchor("Y").flow == pytest.approx(-Q, rel=0.02)


def test_throttle_check_valve_k_positive_restricted_follows_orifice_equation():
    tcv = _throttle_check()
    engine, rv = _pump_relief_circuit(tcv, "X", ["Y"])
    engine.run_until_stable(dt=1.0)
    _assert_healthy(rv, tcv, "X")


def test_throttle_check_valve_k_positive_free_direction_has_no_drop():
    tcv = _throttle_check()
    engine, rv = _pump_relief_circuit(tcv, "Y", ["X"])
    engine.run_until_stable(dt=1.0)
    assert tcv.get_anchor("Y").flow == pytest.approx(Q, rel=0.02)
    assert abs(tcv.get_anchor("X").pressure - tcv.get_anchor("Y").pressure) < 1e3


@pytest.mark.parametrize("cls, ports, state, inlet, outlet", DIRECTIONAL_CASES)
def test_directional_k_positive_follows_orifice_equation(cls, ports, state, inlet, outlet):
    engine, valve, rv = _directional_circuit(cls, ports, state, inlet)
    engine.run_until_stable(dt=1.0)
    _assert_healthy(rv, valve, inlet)
    assert valve.get_anchor(outlet).flow == pytest.approx(-Q, rel=0.02)


def test_throttle_valve_k_positive_equation_residual_unchanged():
    """Same residual as before the k == 0 handling: copysign((Q/k)^2, Q)."""
    tv = _throttle()
    tv.anchors["X"].pressure_var = "P_X"
    tv.anchors["Y"].pressure_var = "P_Y"
    tv.set_scale(1e6, 1e-4)
    idx = {tv.flow_var_x: 0, tv.flow_var_y: 1, "P_X": 2, "P_Y": 3}
    x = np.array([Q, -Q, 3e6, 1e6])
    eq_c, eq_o = tv.equations(x, idx)
    assert eq_c == pytest.approx(0.0, abs=1e-12)
    assert eq_o == pytest.approx((2e6 - HEALTHY_DROP) / tv.p_ref)


# ---------------------------------------------------------------------------
# Validation: k < 0 and missing k
# ---------------------------------------------------------------------------

def _directional_raw(cls, k):
    return cls("dv", domain="hydraulic", properties={"k": k})


@pytest.mark.parametrize("make", [
    pytest.param(lambda k: ThrottleValve("tv", domain="hydraulic", properties={"k": k}), id="ThrottleValve"),
    pytest.param(lambda k: ThrottleCheckValve("tcv", domain="hydraulic", properties={"k": k}), id="ThrottleCheckValve"),
] + [
    pytest.param(lambda k, c=cls: _directional_raw(c, k), id=cls.__name__)
    for cls, _, _ in DIRECTIONAL
])
def test_negative_k_raises_value_error(make):
    with pytest.raises(ValueError, match=r"'k' must be >= 0"):
        make(-1e-7)


@pytest.mark.parametrize("make", [
    pytest.param(lambda: ThrottleValve("tv", domain="hydraulic", properties={}), id="ThrottleValve"),
    pytest.param(lambda: ThrottleCheckValve("tcv", domain="hydraulic", properties={}), id="ThrottleCheckValve"),
] + [
    pytest.param(lambda c=cls: c("dv", domain="hydraulic", properties={}), id=cls.__name__)
    for cls, _, _ in DIRECTIONAL
])
def test_missing_k_still_raises_value_error(make):
    with pytest.raises(ValueError, match=r"required property 'k' is not set"):
        make()


# ---------------------------------------------------------------------------
# GraphBuilder and dialogs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("item_cls, ports", [
    pytest.param(ThrottleValveItem, ("X", "Y"), id="ThrottleValve"),
    pytest.param(ThrottleCheckValveItem, ("X", "Y"), id="ThrottleCheckValve"),
    pytest.param(Valve_4_2_WaysItem, ("P", "A", "B", "R"), id="Valve_4_2_Ways"),
])
def test_graph_builder_accepts_k_zero_with_isolated_ports(item_cls, ports):
    item = item_cls(domain="hydraulic")
    item.properties["k"] = 0.0
    builder = GraphBuilder()
    builder.add_node_from_item(item)
    for port in ports:
        res = ReservoirItem(domain="hydraulic")
        builder.add_node_from_item(res)
        builder.add_connection_from_item(
            ConnectionItem(item, item.anchors[port], res, res.anchors["T"])
        )
    builder.raise_if_errors()  # must not raise
    assert builder.node_map[item].k == 0.0


@pytest.mark.parametrize("item_cls", [
    pytest.param(ThrottleValveItem, id="ThrottleValve"),
    pytest.param(ThrottleCheckValveItem, id="ThrottleCheckValve"),
    pytest.param(Valve_4_2_WaysItem, id="Valve_4_2_Ways"),
])
def test_properties_dialog_k_accepts_zero_rejects_negative(item_cls):
    item = item_cls(domain="hydraulic")
    dialog = item.build_properties_dialog()
    field = dialog._field_k
    field.setText("0")
    assert dialog._validate_field(field) is True
    field.setText("-1e-8")
    assert dialog._validate_field(field) is False
    field.setText("1.5e-8")
    assert dialog._validate_field(field) is True


@pytest.mark.parametrize("item_cls", [
    pytest.param(ThrottleValveItem, id="ThrottleValve"),
    pytest.param(ThrottleCheckValveItem, id="ThrottleCheckValve"),
    pytest.param(Valve_4_2_WaysItem, id="Valve_4_2_Ways"),
])
def test_defect_dialog_k_accepts_zero_rejects_negative(item_cls):
    item = item_cls(domain="hydraulic")
    item.properties["k"] = K
    dialog = item.build_defect_dialog()
    field = dialog.defect_widget("k")
    field.setText("0")
    assert dialog._validate_field(field) is True
    assert dialog.defect_values()["k"] == 0.0
    field.setText("-1e-8")
    assert dialog._validate_field(field) is False
