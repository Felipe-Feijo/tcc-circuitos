import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from simulation.connections import Connection
from simulation.nodes.cylinder.double_acting_cylinder import DoubleActingCylinder
from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
from simulation.nodes.relief_valve import ReliefValve
from simulation.nodes.reservoir import Reservoir
from simulation.simulation_engine import SimulationEngine

Q = 1e-4
C = 1e-11
P_SET = 5e6
PROPS = {"bore": 0.05, "rod_diameter": 0.02, "stroke": 0.2, "external_force": 5000.0}


def _anch(node, *names):
    for name in names:
        node.add_anchor(name, domain="hydraulic")
    return node


def _cyl():
    return _anch(DoubleActingCylinder("cyl", domain="hydraulic", properties=dict(PROPS)), "A", "B")


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
    cyl.handle_command({"action": "set_defect", "leak": -1e-11})
    assert cyl.c_leak == 0.0


def test_pneumatic_ignores_leak():
    cyl = DoubleActingCylinder("cyl", domain="pneumatic")
    cyl.handle_command({"action": "set_defect", "leak": C})
    assert not hasattr(cyl, "c_leak")
    assert cyl.piston_velocity is None


def test_piston_velocity_subtracts_leak():
    cyl = _cyl()
    cyl.c_leak = C
    cyl.anchors["A"].flow = Q
    cyl.anchors["A"].pressure = 3e6
    cyl.anchors["B"].pressure = 1e6
    assert cyl.piston_velocity == pytest.approx((Q - C * 2e6) / cyl.area_a)


def test_conservation_with_leak_is_satisfied_by_leaky_root():
    import numpy as np
    cyl = _cyl()
    cyl.c_leak = C
    cyl.x = 0.1
    cyl.anchors["A"].pressure_var = "P_A"
    cyl.anchors["B"].pressure_var = "P_B"
    idx = {cyl.flow_var_a: 0, cyl.flow_var_b: 1, "P_A": 2, "P_B": 3}
    P_a, P_b = 3e6, 1e6
    Q_l = C * (P_a - P_b)
    v = (Q - Q_l) / cyl.area_a
    Q_b = -(cyl.area_b * v + Q_l)
    _, eq_conservation = cyl.equations(np.array([Q, Q_b, P_a, P_b]), idx)
    assert abs(eq_conservation) < 1e-15


def _circuit():
    """Fixed pump -> A (relief valve on the same line), B -> tank."""
    pump = _anch(FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": Q}), "P", "S")
    cyl = _cyl()
    rv = _anch(ReliefValve("rv", domain="hydraulic", properties={"p_set": P_SET}), "P", "T")
    r1 = _anch(Reservoir("r1", domain="hydraulic", properties={"pressure": 0.0}), "T")
    r2 = _anch(Reservoir("r2", domain="hydraulic", properties={"pressure": 0.0}), "T")
    r3 = _anch(Reservoir("r3", domain="hydraulic", properties={"pressure": 0.0}), "T")
    conns = [
        Connection(pump.get_anchor("S"), r1.get_anchor("T")),
        Connection(pump.get_anchor("P"), cyl.get_anchor("A")),
        Connection(pump.get_anchor("P"), rv.get_anchor("P")),
        Connection(rv.get_anchor("T"), r2.get_anchor("T")),
        Connection(cyl.get_anchor("B"), r3.get_anchor("T")),
    ]
    nodes = {n.id: n for n in (pump, cyl, rv, r1, r2, r3)}
    return SimulationEngine(nodes, {c.id: c for c in conns}), cyl


def _expected_v(cyl):
    a, b = cyl.anchors["A"], cyl.anchors["B"]
    return (a.flow - cyl.c_leak * (a.pressure - b.pressure)) / cyl.area_a


def test_healthy_extension_speed_is_q_over_area():
    engine, cyl = _circuit()
    engine.run_until_stable(dt=0.1)
    assert cyl.piston_velocity == pytest.approx(Q / cyl.area_a, rel=1e-3)


def test_leak_slows_extension():
    engine, cyl = _circuit()
    cyl.handle_command({"action": "set_defect", "leak": C})
    x0 = cyl.x
    engine.run_until_stable(dt=0.1)
    v = cyl.piston_velocity
    assert v == pytest.approx(_expected_v(cyl), rel=1e-6)
    # P_A ~ F/A_A ~ 2.5 MPa -> Q_L ~ 2.5e-5, a quarter of the pump flow
    assert v < 0.85 * Q / cyl.area_a
    assert cyl.x - x0 == pytest.approx(v * 0.1, rel=1e-6)


def test_clear_mid_run_restores_healthy_speed():
    engine, cyl = _circuit()
    cyl.handle_command({"action": "set_defect", "leak": C})
    engine.run_until_stable(dt=0.1)
    cyl.handle_command({"action": "clear_defect"})
    engine.run_until_stable(dt=0.1)
    assert cyl.piston_velocity == pytest.approx(Q / cyl.area_a, rel=1e-3)


def test_leak_at_extended_stop_flows_but_piston_holds():
    engine, cyl = _circuit()
    cyl.handle_command({"action": "set_defect", "leak": C})
    for _ in range(100):
        engine.run_until_stable(dt=0.1)
        if cyl.x >= cyl.stroke:
            break
    assert cyl.x == pytest.approx(cyl.stroke)
    engine.run_until_stable(dt=0.1)
    engine.run_until_stable(dt=0.1)
    assert cyl.x == pytest.approx(cyl.stroke)
    assert abs(cyl.piston_velocity) < 1e-6
    # Pump pressure climbs to the relief setting; the leak keeps flowing.
    assert cyl.anchors["A"].pressure == pytest.approx(P_SET, rel=1e-2)
    assert cyl.anchors["A"].flow == pytest.approx(C * P_SET, rel=2e-2)
