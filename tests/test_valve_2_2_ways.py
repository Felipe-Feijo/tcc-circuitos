import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import math
import pytest
import numpy as np

from simulation.nodes.directional_valve.valve_2_2_ways import Valve_2_2_Ways


def make_valve(k=1e-7, body_state=1):
    valve = Valve_2_2_Ways("v22", domain="hydraulic", properties={"k": k})
    valve.body_state = body_state
    valve.add_anchor("P", domain="hydraulic")
    valve.add_anchor("A", domain="hydraulic")
    valve.anchors["P"].pressure_var = "P_P"
    valve.anchors["A"].pressure_var = "P_A"
    return valve


# ---------------------------------------------------------------------------
# Pneumático
# ---------------------------------------------------------------------------

def test_pneumatic_blocked_at_rest():
    valve = Valve_2_2_Ways("v22", domain="pneumatic", properties={})
    valve.body_state = 0
    assert valve.get_internal_connections() == []


def test_pneumatic_connects_p_a_when_active():
    valve = Valve_2_2_Ways("v22", domain="pneumatic", properties={})
    valve.body_state = 1
    assert valve.get_internal_connections() == [("P", "A")]


# ---------------------------------------------------------------------------
# Contrato hidráulico
# ---------------------------------------------------------------------------

def test_missing_k_raises_value_error_for_hydraulic_domain():
    with pytest.raises(ValueError):
        Valve_2_2_Ways("v22", domain="hydraulic", properties={})


def test_blocked_state_has_no_hydraulic_contract():
    valve = make_valve(body_state=0)
    assert valve.variables == []
    assert valve.hydraulic_ports() == {}
    assert valve.equations(np.array([]), {}) == []


def test_active_state_has_full_hydraulic_contract():
    valve = make_valve(body_state=1)
    assert set(valve.hydraulic_ports().keys()) == {"P", "A"}
    assert set(valve.variables) == {valve.flow_var_in, valve.flow_var_out, "P_P", "P_A"}


def test_active_state_orifice_equation_exact_root():
    k = 1e-7
    valve = make_valve(k=k, body_state=1)
    idx = {valve.flow_var_in: 0, valve.flow_var_out: 1, "P_P": 2, "P_A": 3}

    Q_in = 2e-4
    dp = math.copysign((Q_in / k) ** 2, Q_in)
    x = np.array([Q_in, -Q_in, dp, 0.0])

    eq_flow, eq_dp = valve.equations(x, idx)
    assert abs(eq_flow) < 1e-9
    assert abs(eq_dp) < 1e-6


# ---------------------------------------------------------------------------
# Ponta a ponta
# ---------------------------------------------------------------------------

def test_end_to_end_active_valve_builds_pressure():
    from simulation.simulation_engine import SimulationEngine
    from simulation.nodes.reservoir import Reservoir
    from simulation.nodes.fixed_displacement_pump import FixedDisplacementPump
    from simulation.connections import Connection

    pump = FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": 1e-4})
    pump.add_anchor("P", domain="hydraulic")
    pump.add_anchor("S", domain="hydraulic")

    valve = Valve_2_2_Ways("v22", domain="hydraulic", properties={"k": 1e-7})
    valve.body_state = 1
    valve.add_anchor("P", domain="hydraulic")
    valve.add_anchor("A", domain="hydraulic")

    res_suction = Reservoir("res_suction", domain="hydraulic", properties={"pressure": 0.0})
    res_suction.add_anchor("T", domain="hydraulic")
    res_out = Reservoir("res_out", domain="hydraulic", properties={"pressure": 0.0})
    res_out.add_anchor("T", domain="hydraulic")

    conns = [
        Connection(pump.get_anchor("S"), res_suction.get_anchor("T")),
        Connection(pump.get_anchor("P"), valve.get_anchor("P")),
        Connection(valve.get_anchor("A"), res_out.get_anchor("T")),
    ]
    nodes = {"pump": pump, "v22": valve, "res_suction": res_suction, "res_out": res_out}
    connections = {c.id: c for c in conns}

    engine = SimulationEngine(nodes, connections)
    engine.run_until_stable()

    assert valve.get_anchor("P").pressure > 1000.0
    assert abs(valve.get_anchor("A").flow) > 1e-6


def test_end_to_end_blocked_valve_does_not_crash_and_stays_isolated():
    from simulation.simulation_engine import SimulationEngine
    from simulation.nodes.reservoir import Reservoir
    from simulation.nodes.fixed_displacement_pump import FixedDisplacementPump
    from simulation.connections import Connection

    pump = FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": 1e-4})
    pump.add_anchor("P", domain="hydraulic")
    pump.add_anchor("S", domain="hydraulic")

    valve = Valve_2_2_Ways("v22", domain="hydraulic", properties={"k": 1e-7})
    valve.body_state = 0  # repouso -- bloqueada
    valve.add_anchor("P", domain="hydraulic")
    valve.add_anchor("A", domain="hydraulic")

    res_suction = Reservoir("res_suction", domain="hydraulic", properties={"pressure": 0.0})
    res_suction.add_anchor("T", domain="hydraulic")
    res_out = Reservoir("res_out", domain="hydraulic", properties={"pressure": 0.0})
    res_out.add_anchor("T", domain="hydraulic")

    conns = [
        Connection(pump.get_anchor("S"), res_suction.get_anchor("T")),
        Connection(pump.get_anchor("P"), valve.get_anchor("P")),
        Connection(valve.get_anchor("A"), res_out.get_anchor("T")),
    ]
    nodes = {"pump": pump, "v22": valve, "res_suction": res_suction, "res_out": res_out}
    connections = {c.id: c for c in conns}

    engine = SimulationEngine(nodes, connections)
    engine.run_until_stable()  # não deveria lançar exceção

    assert abs(valve.get_anchor("A").flow) < 1e-9  # lado A isolado, sem fluxo
