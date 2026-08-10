import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

from simulation.nodes.relief_valve import ReliefValve


def make_valve(piloted=False, p_set=1.5e7):
    props = {"p_set": p_set}
    if piloted:
        props["piloted"] = True
    valve = ReliefValve("rv", domain="hydraulic", properties=props)
    valve.add_anchor("P", domain="hydraulic")
    valve.add_anchor("T", domain="hydraulic")
    valve.anchors["P"].pressure_var = "P_P"
    valve.anchors["T"].pressure_var = "P_T"
    if piloted:
        valve.add_anchor("Y", domain="hydraulic")
        valve.anchors["Y"].pressure_var = "P_Y"
    return valve


def make_idx(valve, piloted=False):
    idx = {valve.flow_var_in: 0, valve.flow_var_out: 1, "P_P": 2, "P_T": 3}
    if piloted:
        idx[valve.flow_var_y] = 4
        idx["P_Y"] = 5
    return idx


# ---------------------------------------------------------------------------
# node_type / ports / variables / bounds
# ---------------------------------------------------------------------------

def test_node_type_is_relief_valve():
    valve = make_valve()
    assert valve.type == "relief_valve"


def test_hydraulic_ports_include_y_only_when_piloted():
    valve = make_valve(piloted=False)
    assert set(valve.hydraulic_ports().keys()) == {"P", "T"}

    piloted_valve = make_valve(piloted=True)
    assert set(piloted_valve.hydraulic_ports().keys()) == {"P", "T", "Y"}


def test_variables_include_y_flow_and_pressure_when_piloted():
    valve = make_valve(piloted=False)
    assert set(valve.variables) == {valve.flow_var_in, valve.flow_var_out, "P_P", "P_T"}

    piloted_valve = make_valve(piloted=True)
    assert set(piloted_valve.variables) == {
        piloted_valve.flow_var_in, piloted_valve.flow_var_out, piloted_valve.flow_var_y,
        "P_P", "P_T", "P_Y",
    }


def test_bounds_unaffected_by_piloted():
    valve = make_valve(piloted=False)
    assert valve.bounds == {
        valve.flow_var_in: (0.0, None),
        valve.flow_var_out: (None, 0.0),
    }

    piloted_valve = make_valve(piloted=True)
    assert piloted_valve.bounds == {
        piloted_valve.flow_var_in: (0.0, None),
        piloted_valve.flow_var_out: (None, 0.0),
    }


# ---------------------------------------------------------------------------
# Regressão -- comportamento não pilotado idêntico ao de antes do rename
# ---------------------------------------------------------------------------

def test_non_piloted_closed_regime_is_exact_root_below_p_set():
    valve = make_valve(piloted=False, p_set=1.5e7)
    idx = make_idx(valve)
    x = np.array([0.0, 0.0, 1.0e7, 0.0])  # P_in bem abaixo de p_set, Q=0
    eq_conservation, eq_fb = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_fb) < 1e-9


def test_non_piloted_open_regime_is_exact_root_above_p_set():
    valve = make_valve(piloted=False, p_set=1.5e7)
    idx = make_idx(valve)
    x = np.array([1e-4, -1e-4, 2e7, 2e7])  # P_in == P_out == 2e7 > p_set
    eq_conservation, eq_fb = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_fb) < 1e-9


# ---------------------------------------------------------------------------
# Pilotagem -- limiar efetivo = p_set + P_y
# ---------------------------------------------------------------------------

def test_closed_regime_residual_uses_effective_threshold_with_pilot():
    """No mesmo P_in, acima de p_set sozinho mas abaixo de p_set + P_y:
    sem pilotagem o regime fechado (Q=0) NÃO é raiz (a válvula "quer"
    abrir); com pilotagem suficiente, volta a ser raiz (permanece
    fechada)."""
    p_set = 1.5e7
    p_in = 1.55e7  # acima de p_set sozinho

    valve = make_valve(piloted=False, p_set=p_set)
    idx = make_idx(valve)
    x = np.array([0.0, 0.0, p_in, 0.0])
    _, eq_fb = valve.equations(x, idx)
    assert abs(eq_fb) > 1e-6  # não é raiz -- P_in já passou de p_set sozinho

    piloted_valve = make_valve(piloted=True, p_set=p_set)
    idx2 = make_idx(piloted_valve, piloted=True)
    p_y = 1e6  # 10 bar -- eleva o limiar efetivo pra 1.6e7, acima de P_in
    x2 = np.array([0.0, 0.0, p_in, 0.0, 0.0, p_y])
    eq_conservation, eq_fb2, eq_y = piloted_valve.equations(x2, idx2)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_fb2) < 1e-9  # com o piloto, o limiar sobe e a raiz fechada volta a valer
    assert abs(eq_y) < 1e-9


def test_piloted_open_regime_also_uses_effective_threshold():
    """No regime aberto, o gate `P_out > effective_p_set` também precisa
    considerar P_y -- senão a válvula abriria cedo demais mesmo com
    pilotagem alta."""
    p_set = 1.5e7
    p_y = 1e6  # eleva o limiar efetivo pra 1.6e7

    valve = make_valve(piloted=True, p_set=p_set)
    idx = make_idx(valve, piloted=True)
    # P_out = 1.55e7 (> p_set sozinho, mas < p_set + p_y) -- não deveria
    # satisfazer o gate de regime aberto.
    x = np.array([0.0, 0.0, 1.55e7, 1.55e7, 0.0, p_y])
    _, eq_fb, _ = valve.equations(x, idx)
    # No regime fechado com Q_in=0: a = (effective_p_set - P_in)/P_scale > 0, b=0 -> raiz.
    assert abs(eq_fb) < 1e-9


def test_y_port_has_zero_flow_equation():
    valve = make_valve(piloted=True)
    idx = make_idx(valve, piloted=True)
    x = np.array([0.0, 0.0, 0.0, 0.0, 7.0, 0.0])  # Q_Y = 7 (não deveria ser raiz)
    eqs = valve.equations(x, idx)
    eq_y = eqs[-1]
    assert abs(eq_y - 7.0 / valve.q_ref) < 1e-9
