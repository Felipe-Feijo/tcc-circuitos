import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import math
import pytest
import numpy as np

from simulation.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways
from simulation.nodes.directional_valve.valve_5_2_ways import Valve_5_2_Ways


def make_4_2(k=1e-7, body_state=0):
    valve = Valve_4_2_Ways("v42", domain="hydraulic", properties={"k": k})
    valve.body_state = body_state
    for port in ("P", "A", "B", "R"):
        valve.add_anchor(port, domain="hydraulic")
        valve.anchors[port].pressure_var = f"P_{port}"
    return valve


def make_5_2(k=1e-7, body_state=0):
    valve = Valve_5_2_Ways("v52", domain="hydraulic", properties={"k": k})
    valve.body_state = body_state
    for port in ("P", "A", "B", "R1", "R2"):
        valve.add_anchor(port, domain="hydraulic")
        valve.anchors[port].pressure_var = f"P_{port}"
    return valve


# ---------------------------------------------------------------------------
# Contrato -- k obrigatório, ports/variables incluem todas as portas sempre
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls", [Valve_4_2_Ways, Valve_5_2_Ways])
def test_missing_k_raises_value_error_for_hydraulic_domain(cls):
    with pytest.raises(ValueError):
        cls(cls.__name__, domain="hydraulic", properties={})


def test_4_2_hydraulic_ports_include_all_four_ports_regardless_of_state():
    valve = make_4_2(body_state=0)
    assert set(valve.hydraulic_ports().keys()) == {"P", "A", "B", "R"}
    valve.body_state = 1
    assert set(valve.hydraulic_ports().keys()) == {"P", "A", "B", "R"}


def test_5_2_hydraulic_ports_include_all_five_ports_regardless_of_state():
    valve = make_5_2(body_state=0)
    assert set(valve.hydraulic_ports().keys()) == {"P", "A", "B", "R1", "R2"}
    valve.body_state = 1
    assert set(valve.hydraulic_ports().keys()) == {"P", "A", "B", "R1", "R2"}


def test_4_2_variables_include_flow_and_pressure_vars():
    valve = make_4_2()
    assert set(valve.variables) == {
        "Q_v42_P", "Q_v42_A", "Q_v42_B", "Q_v42_R",
        "P_P", "P_A", "P_B", "P_R",
    }


def test_pneumatic_domain_has_no_hydraulic_contract():
    valve = Valve_4_2_Ways("v42", domain="pneumatic", properties={})
    assert valve.variables == []
    assert valve.hydraulic_ports() == {}


# ---------------------------------------------------------------------------
# Equações -- cada par ativo tem sua própria conservação + orifício
# ---------------------------------------------------------------------------

def _idx_for(valve, ports):
    idx = {}
    for i, port in enumerate(ports):
        idx[valve._flow_vars[port]] = 2 * i
        idx[valve.anchors[port].pressure_var] = 2 * i + 1
    return idx


def test_4_2_state0_pairs_are_p_a_and_b_r():
    """Confere as duas equações de par (P-A e B-R) simultaneamente, cada
    uma numa raiz exata calculada à mão de forma independente."""
    k = 1e-7
    valve = make_4_2(k=k, body_state=0)
    assert valve.get_internal_connections() == [("P", "A"), ("B", "R")]

    idx = {
        "Q_v42_P": 0, "P_P": 1,
        "Q_v42_A": 2, "P_A": 3,
        "Q_v42_B": 4, "P_B": 5,
        "Q_v42_R": 6, "P_R": 7,
    }
    x = np.zeros(8)

    Q_p = 1e-4
    dp_pa = math.copysign((Q_p / k) ** 2, Q_p)
    x[idx["Q_v42_P"]] = Q_p
    x[idx["Q_v42_A"]] = -Q_p
    x[idx["P_P"]] = dp_pa
    x[idx["P_A"]] = 0.0

    Q_b = 5e-5
    dp_br = math.copysign((Q_b / k) ** 2, Q_b)
    x[idx["Q_v42_B"]] = Q_b
    x[idx["Q_v42_R"]] = -Q_b
    x[idx["P_B"]] = dp_br
    x[idx["P_R"]] = 0.0

    eqs = valve.equations(x, idx)
    assert len(eqs) == 4  # 2 pares x (conservação + orifício)

    eq_flow_pa, eq_dp_pa, eq_flow_br, eq_dp_br = eqs
    assert abs(eq_flow_pa) < 1e-9
    assert abs(eq_dp_pa) < 1e-6
    assert abs(eq_flow_br) < 1e-9
    assert abs(eq_dp_br) < 1e-6


def test_4_2_state1_pairs_are_p_b_and_a_r():
    valve = make_4_2(body_state=1)
    assert valve.get_internal_connections() == [("P", "B"), ("A", "R")]


def test_5_2_state0_pairs_are_p_b_and_a_r1():
    valve = make_5_2(body_state=0)
    assert valve.get_internal_connections() == [("P", "B"), ("A", "R1")]


def test_5_2_state1_pairs_are_p_a_and_b_r2():
    valve = make_5_2(body_state=1)
    assert valve.get_internal_connections() == [("P", "A"), ("B", "R2")]


def test_5_2_orifice_equation_exact_root():
    """Confere a equação de um dos pares (P-A, estado 1) num ponto que é
    raiz exata calculada à mão -- mesma equação de orifício da 3/2 vias."""
    k = 1e-7
    valve = make_5_2(k=k, body_state=1)
    assert valve.get_internal_connections()[0] == ("P", "A")

    Q_p = 2e-4
    dp = math.copysign((Q_p / k) ** 2, Q_p)
    idx = {
        "Q_v52_P": 0, "P_P": 1,
        "Q_v52_A": 2, "P_A": 3,
        "Q_v52_B": 4, "P_B": 5,
        "Q_v52_R1": 6, "P_R1": 7,
        "Q_v52_R2": 8, "P_R2": 9,
    }
    x = np.zeros(10)
    x[idx["Q_v52_P"]] = Q_p
    x[idx["Q_v52_A"]] = -Q_p
    x[idx["P_P"]] = dp
    x[idx["P_A"]] = 0.0

    # segundo par (B-R2) -- também precisa ser consistente pra não afetar
    # o teste (mas equations() é avaliado par a par, então cada par só usa
    # suas próprias variáveis)
    Q_b = 5e-5
    dp2 = math.copysign((Q_b / k) ** 2, Q_b)
    x[idx["Q_v52_B"]] = Q_b
    x[idx["Q_v52_R2"]] = -Q_b
    x[idx["P_B"]] = dp2
    x[idx["P_R2"]] = 0.0

    eqs = valve.equations(x, idx)
    assert len(eqs) == 4
    eq_flow_pa, eq_dp_pa, eq_flow_br2, eq_dp_br2 = eqs
    assert abs(eq_flow_pa) < 1e-9
    assert abs(eq_dp_pa) < 1e-6
    assert abs(eq_flow_br2) < 1e-9
    assert abs(eq_dp_br2) < 1e-6


# ---------------------------------------------------------------------------
# Ponta a ponta: bomba -> 4/2 vias -> reservatórios (dois pares simultâneos
# compartilhando o mesmo nó -- a complexidade nova que a 3/2 não tem)
# ---------------------------------------------------------------------------

def test_4_2_end_to_end_active_pair_builds_pressure_idle_pair_stays_at_zero():
    from simulation.simulation_engine import SimulationEngine
    from simulation.nodes.reservoir import Reservoir
    from simulation.nodes.fixed_displacement_pump import FixedDisplacementPump
    from simulation.connections import Connection

    pump = FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": 1e-4})
    pump.add_anchor("P", domain="hydraulic")
    pump.add_anchor("S", domain="hydraulic")

    valve = Valve_4_2_Ways("v42", domain="hydraulic", properties={"k": 1e-7})
    for port in ("P", "A", "B", "R"):
        valve.add_anchor(port, domain="hydraulic")
    valve.body_state = 0  # par ativo: P-A ; par ocioso: B-R

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

    nodes = {"pump": pump, "v42": valve, "res_suction": res_suction,
             "res_a": res_a, "res_b": res_b, "res_r": res_r}
    connections = {c.id: c for c in conns}

    engine = SimulationEngine(nodes, connections)
    engine.run_until_stable()

    # Par ativo (P-A): a bomba força vazão através do orifício -- pressão sobe.
    assert valve.get_anchor("P").pressure > 1000.0
    assert abs(valve.get_anchor("A").flow) > 1e-6

    # Par ocioso (B-R): nada empurrando fluxo ali -- fica parado em zero.
    assert abs(valve.get_anchor("B").flow) < 1e-9
    assert abs(valve.get_anchor("R").flow) < 1e-9
