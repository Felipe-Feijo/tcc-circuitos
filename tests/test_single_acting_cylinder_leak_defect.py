import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from simulation.connections import Connection
from simulation.nodes.cylinder.single_acting_cylinder import SingleActingCylinder
from simulation.nodes.directional_valve.valve_2_2_ways import Valve_2_2_Ways
from simulation.nodes.reservoir import Reservoir
from simulation.simulation_engine import SimulationEngine

C = 1e-10
PROPS = {
    "bore": 0.05, "stroke": 0.2, "spring_k": 1000.0,
    "external_force": 500.0, "default_state": "extended",
}


def _anch(node, *names):
    for name in names:
        node.add_anchor(name, domain="hydraulic")
    return node


def _cyl():
    return _anch(SingleActingCylinder("sa", domain="hydraulic", properties=dict(PROPS)), "A")


def test_fresh_cylinder_has_no_defect():
    cyl = _cyl()
    assert cyl.c_leak == 0.0
    assert cyl.defect_active is False


def test_set_and_clear_leak():
    cyl = _cyl()
    cyl.handle_command({"action": "set_defect", "leak": C})
    assert cyl.c_leak == pytest.approx(C)
    assert cyl.defect_active is True
    cyl.handle_command({"action": "clear_defect"})
    assert cyl.c_leak == 0.0
    assert cyl.defect_active is False


def test_negative_leak_clamps_to_zero():
    cyl = _cyl()
    cyl.handle_command({"action": "set_defect", "leak": -C})
    assert cyl.c_leak == 0.0


def test_pneumatic_ignores_leak():
    cyl = SingleActingCylinder("sa", domain="pneumatic")
    cyl.handle_command({"action": "set_defect", "leak": C})
    assert not hasattr(cyl, "c_leak")
    assert cyl.piston_velocity is None


def test_piston_velocity_subtracts_leak():
    cyl = _cyl()
    cyl.c_leak = C
    cyl.anchors["A"].flow = 1e-5
    cyl.anchors["A"].pressure = 4e5
    assert cyl.piston_velocity == pytest.approx((1e-5 - C * 4e5) / cyl.area)


def test_extended_stop_bound_dropped_only_with_leak():
    cyl = _cyl()
    assert cyl.bounds == {cyl.flow_var: (None, 0.0)}
    cyl.c_leak = C
    assert cyl.bounds == {}


def _blocked_circuit():
    """Extended cylinder whose port A dead-ends at a closed 2/2 valve."""
    cyl = _cyl()
    valve = _anch(Valve_2_2_Ways("v", domain="hydraulic", properties={"k": 1e-7}), "P", "A")
    res = _anch(Reservoir("r", domain="hydraulic", properties={"pressure": 0.0}), "T")
    conns = [
        Connection(cyl.get_anchor("A"), valve.get_anchor("A")),
        Connection(valve.get_anchor("P"), res.get_anchor("T")),
    ]
    nodes = {n.id: n for n in (cyl, valve, res)}
    return SimulationEngine(nodes, {c.id: c for c in conns}), cyl


def test_healthy_blocked_cylinder_holds():
    engine, cyl = _blocked_circuit()
    for _ in range(5):
        engine.run_until_stable(dt=0.1)
    assert cyl.x == pytest.approx(cyl.stroke)


def test_leak_makes_blocked_cylinder_sink():
    engine, cyl = _blocked_circuit()
    cyl.handle_command({"action": "set_defect", "leak": C})
    xs = [cyl.x]
    for _ in range(5):
        engine.run_until_stable(dt=0.1)
        xs.append(cyl.x)
    assert all(b < a for a, b in zip(xs, xs[1:]))
    # Port blocked (Q = 0): v = -c * P_A / A, P_A held by spring + load.
    P_a = cyl.anchors["A"].pressure
    assert P_a == pytest.approx((cyl.spring_k * cyl.x + cyl.external_force) / cyl.area, rel=2e-2)
    assert cyl.piston_velocity == pytest.approx(-C * P_a / cyl.area, rel=2e-2)


def _pump_circuit():
    """Fixed pump -> A with a relief valve on the same line."""
    from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
    from simulation.nodes.relief_valve import ReliefValve
    props = dict(PROPS, default_state="retracted")
    cyl = _anch(SingleActingCylinder("sa", domain="hydraulic", properties=props), "A")
    pump = _anch(FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": 1e-4}), "P", "S")
    rv = _anch(ReliefValve("rv", domain="hydraulic", properties={"p_set": 5e6}), "P", "T")
    r1 = _anch(Reservoir("r1", domain="hydraulic", properties={"pressure": 0.0}), "T")
    r2 = _anch(Reservoir("r2", domain="hydraulic", properties={"pressure": 0.0}), "T")
    conns = [
        Connection(pump.get_anchor("S"), r1.get_anchor("T")),
        Connection(pump.get_anchor("P"), cyl.get_anchor("A")),
        Connection(pump.get_anchor("P"), rv.get_anchor("P")),
        Connection(rv.get_anchor("T"), r2.get_anchor("T")),
    ]
    nodes = {n.id: n for n in (cyl, pump, rv, r1, r2)}
    return SimulationEngine(nodes, {c.id: c for c in conns}), cyl


def test_leak_at_extended_stop_under_pump_holds_and_flows():
    """Covers the dropped extended-stop bound: with Q = c*P > 0 the
    piston must still sit at the stop while the leak keeps flowing."""
    engine, cyl = _pump_circuit()
    leak = 1e-11
    cyl.handle_command({"action": "set_defect", "leak": leak})
    for _ in range(80):
        engine.run_until_stable(dt=0.1)
        assert cyl.x <= cyl.stroke
    assert cyl.x == pytest.approx(cyl.stroke)
    assert abs(cyl.piston_velocity) < 1e-6
    assert cyl.anchors["A"].pressure == pytest.approx(5e6, rel=1e-2)
    assert cyl.anchors["A"].flow == pytest.approx(leak * 5e6, rel=2e-2)
