import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import math
import pytest
import numpy as np

from simulation.nodes.directional_valve.valve_4_3_ways import Valve_4_3_Ways


def make_valve(k=1e-7, body_state=1):
    valve = Valve_4_3_Ways("v43", domain="hydraulic", properties={"k": k})
    valve.body_state = body_state
    for port in ("P", "A", "B", "R"):
        valve.add_anchor(port, domain="hydraulic")
        valve.anchors[port].pressure_var = f"P_{port}"
    return valve


def test_is_three_position():
    valve = Valve_4_3_Ways("v43", domain="pneumatic", properties={})
    assert valve.THREE_POSITION is True
    assert valve.body_state == 1  # repouso -- centro


def test_missing_k_raises_value_error_for_hydraulic_domain():
    with pytest.raises(ValueError):
        Valve_4_3_Ways("v43", domain="hydraulic", properties={})


def test_state0_pairs_are_p_a_and_b_r():
    valve = make_valve(body_state=0)
    assert valve.get_internal_connections() == [("P", "A"), ("B", "R")]


def test_state2_pairs_are_p_b_and_a_r():
    valve = make_valve(body_state=2)
    assert valve.get_internal_connections() == [("P", "B"), ("A", "R")]


def test_state1_center_has_no_pairs():
    valve = make_valve(body_state=1)
    assert valve.get_internal_connections() == []


def test_hydraulic_ports_include_all_four_ports_regardless_of_state():
    for state in (0, 1, 2):
        valve = make_valve(body_state=state)
        assert set(valve.hydraulic_ports().keys()) == {"P", "A", "B", "R"}


def test_pneumatic_domain_has_no_hydraulic_contract():
    valve = Valve_4_3_Ways("v43", domain="pneumatic", properties={})
    assert valve.variables == []
    assert valve.hydraulic_ports() == {}


def test_state0_orifice_equation_exact_root():
    k = 1e-7
    valve = make_valve(k=k, body_state=0)
    idx = {
        "Q_v43_P": 0, "P_P": 1,
        "Q_v43_A": 2, "P_A": 3,
        "Q_v43_B": 4, "P_B": 5,
        "Q_v43_R": 6, "P_R": 7,
    }
    x = np.zeros(8)

    Q_p = 1e-4
    dp_pa = math.copysign((Q_p / k) ** 2, Q_p)
    x[idx["Q_v43_P"]] = Q_p
    x[idx["Q_v43_A"]] = -Q_p
    x[idx["P_P"]] = dp_pa
    x[idx["P_A"]] = 0.0

    Q_b = 5e-5
    dp_br = math.copysign((Q_b / k) ** 2, Q_b)
    x[idx["Q_v43_B"]] = Q_b
    x[idx["Q_v43_R"]] = -Q_b
    x[idx["P_B"]] = dp_br
    x[idx["P_R"]] = 0.0

    eqs = valve.equations(x, idx)
    assert len(eqs) == 4
    eq_flow_pa, eq_dp_pa, eq_flow_br, eq_dp_br = eqs
    assert abs(eq_flow_pa) < 1e-9
    assert abs(eq_dp_pa) < 1e-6
    assert abs(eq_flow_br) < 1e-9
    assert abs(eq_dp_br) < 1e-6


def test_state1_center_forces_zero_flow_on_all_four_ports():
    valve = make_valve(body_state=1)
    idx = {
        "Q_v43_P": 0, "P_P": 1,
        "Q_v43_A": 2, "P_A": 3,
        "Q_v43_B": 4, "P_B": 5,
        "Q_v43_R": 6, "P_R": 7,
    }
    x = np.zeros(8)
    x[idx["Q_v43_P"]] = 1e-4  # deveria ser forçado a 0 pela equação

    eqs = valve.equations(x, idx)
    assert len(eqs) == 4  # uma equação Q=0 por porto, nenhuma de orifício
    assert abs(eqs[0] - (1e-4 / valve.q_ref)) < 1e-12  # eq. é só Q/Q_scale


def test_end_to_end_center_isolates_all_four_ports_no_crash():
    from simulation.simulation_engine import SimulationEngine
    from simulation.nodes.reservoir import Reservoir
    from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
    from simulation.connections import Connection

    pump = FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": 1e-4})
    pump.add_anchor("P", domain="hydraulic")
    pump.add_anchor("S", domain="hydraulic")

    valve = Valve_4_3_Ways("v43", domain="hydraulic", properties={"k": 1e-7})
    for port in ("P", "A", "B", "R"):
        valve.add_anchor(port, domain="hydraulic")
    valve.body_state = 1  # centro fechado

    res_suction = Reservoir("res_suction", domain="hydraulic", properties={"pressure": 0.0})
    res_suction.add_anchor("T", domain="hydraulic")
    res_a = Reservoir("res_a", domain="hydraulic", properties={"pressure": 0.0})
    res_a.add_anchor("T", domain="hydraulic")
    res_b = Reservoir("res_b", domain="hydraulic", properties={"pressure": 0.0})
    res_b.add_anchor("T", domain="hydraulic")
    res_r = Reservoir("res_r", domain="hydraulic", properties={"pressure": 0.0})
    res_r.add_anchor("T", domain="hydraulic")

    conns = [
        Connection(pump.get_anchor("S"), res_suction.get_anchor("T")),
        Connection(pump.get_anchor("P"), valve.get_anchor("P")),
        Connection(valve.get_anchor("A"), res_a.get_anchor("T")),
        Connection(valve.get_anchor("B"), res_b.get_anchor("T")),
        Connection(valve.get_anchor("R"), res_r.get_anchor("T")),
    ]

    nodes = {"pump": pump, "v43": valve, "res_suction": res_suction,
             "res_a": res_a, "res_b": res_b, "res_r": res_r}
    connections = {c.id: c for c in conns}

    engine = SimulationEngine(nodes, connections)
    engine.run_until_stable()  # não deve lançar exceção (sistema mal-posto)

    assert abs(valve.get_anchor("A").flow) < 1e-9
    assert abs(valve.get_anchor("B").flow) < 1e-9
    assert abs(valve.get_anchor("R").flow) < 1e-9
