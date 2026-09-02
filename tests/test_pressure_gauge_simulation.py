import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np


def make_gauge(domain="hydraulic"):
    from simulation.nodes.pressure_gauge import PressureGauge
    gauge = PressureGauge("g1", domain=domain)
    gauge.add_anchor("P", domain=domain)
    return gauge


# ---------------------------------------------------------------------------
# Hidráulico -- porta morta (mesma técnica do pino Z do check valve piloted)
# ---------------------------------------------------------------------------

def test_hydraulic_ports_returns_dead_port():
    gauge = make_gauge("hydraulic")
    assert gauge.hydraulic_ports() == {"P": gauge.flow_var}


def test_variables_includes_flow_and_pressure_vars():
    gauge = make_gauge("hydraulic")
    gauge.anchors["P"].pressure_var = "P_g1_P"
    assert set(gauge.variables) == {gauge.flow_var, "P_g1_P"}


def test_equations_root_is_zero_flow():
    gauge = make_gauge("hydraulic")
    gauge.set_scale(p_ref=1e7, q_ref=1e-4)
    idx = {gauge.flow_var: 0}
    x = np.array([0.0])
    (residual,) = gauge.equations(x, idx)
    assert residual == pytest.approx(0.0)


def test_equations_nonzero_residual_when_flow_nonzero():
    gauge = make_gauge("hydraulic")
    gauge.set_scale(p_ref=1e7, q_ref=1e-4)
    idx = {gauge.flow_var: 0}
    x = np.array([1e-4])
    (residual,) = gauge.equations(x, idx)
    assert abs(residual) > 1e-2


def test_get_visual_state_returns_pressure_in_hydraulic_domain():
    gauge = make_gauge("hydraulic")
    gauge.anchors["P"].pressure = 5e6
    assert gauge.get_visual_state() == pytest.approx(5e6)


# ---------------------------------------------------------------------------
# Pneumático -- sem equações próprias, só lê o state propagado
# ---------------------------------------------------------------------------

def test_pneumatic_domain_has_no_hydraulic_ports():
    gauge = make_gauge("pneumatic")
    assert gauge.hydraulic_ports() == {}


def test_get_visual_state_returns_state_bool_in_pneumatic_domain():
    gauge = make_gauge("pneumatic")
    gauge.anchors["P"].state = True
    assert gauge.get_visual_state() is True


# ---------------------------------------------------------------------------
# Ponta a ponta: gauge conectado em paralelo lê a pressão do circuito
# ---------------------------------------------------------------------------

def test_gauge_reads_shared_pressure_end_to_end():
    from simulation.simulation_engine import SimulationEngine
    from simulation.nodes.accumulator import Accumulator
    from simulation.nodes.reservoir import Reservoir
    from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
    from simulation.nodes.pressure_gauge import PressureGauge
    from simulation.connections import Connection

    pump = FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": 1e-4})
    pump.add_anchor("P", domain="hydraulic")
    pump.add_anchor("S", domain="hydraulic")

    res_suction = Reservoir("res_suction", domain="hydraulic", properties={"pressure": 0.0})
    res_suction.add_anchor("T", domain="hydraulic")

    acc = Accumulator("acc", domain="hydraulic", properties={"V0": 1e-3, "P0": 3e6})
    acc.add_anchor("P", domain="hydraulic")

    gauge = PressureGauge("gauge", domain="hydraulic")
    gauge.add_anchor("P", domain="hydraulic")

    conn1 = Connection(pump.get_anchor("S"), res_suction.get_anchor("T"))
    conn2 = Connection(pump.get_anchor("P"), acc.get_anchor("P"))
    conn3 = Connection(pump.get_anchor("P"), gauge.get_anchor("P"))

    nodes = {"pump": pump, "res_suction": res_suction, "acc": acc, "gauge": gauge}
    connections = {c.id: c for c in (conn1, conn2, conn3)}

    engine = SimulationEngine(nodes, connections)
    engine.run_until_stable(dt=1.0)

    assert gauge.get_anchor("P").pressure == pytest.approx(3e6, rel=1e-3)
