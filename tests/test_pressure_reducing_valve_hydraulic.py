import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

from simulation.nodes.pressure_reducing_valve import PressureReducingValve


def make_valve(p_set=1.5e7):
    valve = PressureReducingValve("prv", domain="hydraulic", properties={"p_set": p_set})
    valve.add_anchor("P", domain="hydraulic")
    valve.add_anchor("A", domain="hydraulic")
    valve.anchors["P"].pressure_var = "P_P"
    valve.anchors["A"].pressure_var = "P_A"
    return valve


def make_idx(valve):
    return {valve.flow_var_p: 0, valve.flow_var_a: 1, "P_P": 2, "P_A": 3}


# ---------------------------------------------------------------------------
# node_type / ports / variables / bounds
# ---------------------------------------------------------------------------

def test_node_type_is_pressure_reducing_valve():
    valve = make_valve()
    assert valve.type == "pressure_reducing_valve"


def test_hydraulic_ports_are_p_and_a():
    valve = make_valve()
    assert valve.hydraulic_ports() == {"P": valve.flow_var_p, "A": valve.flow_var_a}


def test_variables_include_flows_and_pressures():
    valve = make_valve()
    assert set(valve.variables) == {valve.flow_var_p, valve.flow_var_a, "P_P", "P_A"}


def test_bounds_restrict_to_forward_flow_only():
    valve = make_valve()
    assert valve.bounds == {
        valve.flow_var_p: (0.0, None),
        valve.flow_var_a: (None, 0.0),
    }


def test_p_hint_is_p_set():
    valve = make_valve(p_set=2e7)
    assert valve.p_hint == 2e7


def test_missing_p_set_raises_value_error():
    try:
        PressureReducingValve("prv2", domain="hydraulic", properties={})
        assert False, "expected ValueError for missing p_set"
    except ValueError as e:
        assert "p_set" in str(e)


# ---------------------------------------------------------------------------
# Regime 1: fully open (P_A == P_P), while P_A stays below p_set
# ---------------------------------------------------------------------------

def test_fully_open_regime_is_exact_root_below_p_set():
    valve = make_valve(p_set=1.5e7)
    idx = make_idx(valve)
    # P_P == P_A == 1e7, well below p_set -- no throttling needed.
    x = np.array([1e-4, -1e-4, 1.0e7, 1.0e7])
    eq_conservation, eq_fb = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_fb) < 1e-9


def test_fully_open_regime_breaks_once_p_a_would_exceed_p_set():
    """Sanity check that the fully-open assumption (P_A == P_P) stops being
    a root once that would push P_A above p_set -- confirms the FB equation
    actually gates the open regime instead of always returning 0."""
    valve = make_valve(p_set=1.5e7)
    idx = make_idx(valve)
    x = np.array([1e-4, -1e-4, 2e7, 2e7])  # P_P == P_A == 2e7 > p_set
    _, eq_fb = valve.equations(x, idx)
    assert abs(eq_fb) > 1e-6  # not a root -- violates a>=0 (p_set - P_A < 0)


# ---------------------------------------------------------------------------
# Regime 2: regulating (P_A held at p_set, P_P >= P_A)
# ---------------------------------------------------------------------------

def test_regulating_regime_is_exact_root_when_supply_exceeds_setpoint():
    valve = make_valve(p_set=1.5e7)
    idx = make_idx(valve)
    # P_A held at p_set, P_P above it -- valve throttling.
    x = np.array([1e-4, -1e-4, 2.0e7, 1.5e7])
    eq_conservation, eq_fb = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_fb) < 1e-9


def test_regulating_regime_not_a_root_if_p_a_drifts_from_setpoint():
    valve = make_valve(p_set=1.5e7)
    idx = make_idx(valve)
    # P_P above p_set (so b > 0), but P_A hasn't settled at p_set (a > 0 too)
    # -- both terms positive means neither complementarity slot is zero.
    x = np.array([1e-4, -1e-4, 2.0e7, 1.4e7])
    _, eq_fb = valve.equations(x, idx)
    assert abs(eq_fb) > 1e-6


# ---------------------------------------------------------------------------
# Regime 3: closed (outlet pushed above p_set externally, no forward flow)
# ---------------------------------------------------------------------------

def test_closed_regime_is_exact_root_when_outlet_exceeds_setpoint_with_no_flow():
    """P_A pushed above p_set externally, Q_p already at its zero lower
    bound -- the valve should hold Q_p=0 rather than have no root."""
    valve = make_valve(p_set=1.5e7)
    idx = make_idx(valve)
    x = np.array([0.0, 0.0, 1.0e7, 1.6e7])  # P_p < P_a, P_a > p_set, Q_p=0
    eq_conservation, eq_fb = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_fb) < 1e-9


# ---------------------------------------------------------------------------
# Conservation holds regardless of regime
# ---------------------------------------------------------------------------

def test_conservation_residual_scales_with_imbalance():
    valve = make_valve(p_set=1.5e7)
    idx = make_idx(valve)
    x = np.array([5e-4, -1e-4, 1.0e7, 1.0e7])  # Q_P + Q_A = 4e-4, not conserved
    eq_conservation, _ = valve.equations(x, idx)
    assert abs(eq_conservation - 4e-4 / valve.q_ref) < 1e-12


# ---------------------------------------------------------------------------
# initial_guess / set_scale
# ---------------------------------------------------------------------------

def test_initial_guess_seeds_zero_flow_and_p_anchor_pressure():
    valve = make_valve(p_set=1.5e7)
    valve.anchors["P"].pressure = 3e7
    guess = valve.initial_guess
    assert guess[valve.flow_var_p] == 0.0
    assert guess[valve.flow_var_a] == 0.0
    assert guess["P_P"] == 3e7


def test_set_scale_applies_minimum_floors():
    valve = make_valve()
    valve.set_scale(p_ref=10.0, q_ref=1e-15)
    assert valve.p_ref == 1e5   # floor: 1 bar
    assert valve.q_ref == 1e-10  # floor


# ---------------------------------------------------------------------------
# relieving=True: T port, 3-port conservation, relief regime
# ---------------------------------------------------------------------------

def make_relieving_valve(p_set=1.5e7):
    valve = PressureReducingValve(
        "prv", domain="hydraulic", properties={"p_set": p_set, "relieving": True},
    )
    valve.add_anchor("P", domain="hydraulic")
    valve.add_anchor("A", domain="hydraulic")
    valve.add_anchor("T", domain="hydraulic")
    valve.anchors["P"].pressure_var = "P_P"
    valve.anchors["A"].pressure_var = "P_A"
    valve.anchors["T"].pressure_var = "P_T"
    return valve


def make_relieving_idx(valve):
    return {
        valve.flow_var_p: 0, valve.flow_var_a: 1, valve.flow_var_t: 2,
        "P_P": 3, "P_A": 4, "P_T": 5,
    }


def test_relieving_false_by_default_no_t_port():
    valve = make_valve()
    assert valve.relieving is False
    assert not hasattr(valve, "flow_var_t")
    assert set(valve.hydraulic_ports().keys()) == {"P", "A"}


def test_relieving_true_adds_t_port():
    valve = make_relieving_valve()
    assert valve.relieving is True
    assert set(valve.hydraulic_ports().keys()) == {"P", "A", "T"}


def test_variables_include_t_flow_and_pressure_when_relieving():
    valve = make_relieving_valve(p_set=2e7)
    assert set(valve.variables) == {
        valve.flow_var_p, valve.flow_var_a, valve.flow_var_t, "P_P", "P_A", "P_T",
    }


def test_bounds_include_t_when_relieving():
    valve = make_relieving_valve()
    assert valve.bounds == {
        valve.flow_var_p: (0.0, None),
        valve.flow_var_a: (None, 0.0),
        valve.flow_var_t: (None, 0.0),
    }


def test_relieving_conservation_is_3_port():
    valve = make_relieving_valve(p_set=1.5e7)
    idx = make_relieving_idx(valve)
    # Q_P + Q_A + Q_T = 2e-4 - 1e-4 - 1e-4 = 0
    x = np.array([2e-4, -1e-4, -1e-4, 1.0e7, 1.0e7, 0.0])
    eq_conservation, _, _ = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9


def test_relief_regime_residual_matches_formula():
    """Inside the closed/relief branch (P_a > p_set, Q_p <= 0), eq_relief
    should equal exactly (P_a - p_set)/P_scale. Not asserted at zero: the
    branch's own root (P_a == p_set) sits exactly on its guard's boundary
    (P_a > p_set), which no floating trial value can land on exactly --
    a converging solver approaches it from above without ever crossing it.
    Check the formula directly instead of asserting an exact root here."""
    valve = make_relieving_valve(p_set=1.5e7)
    idx = make_relieving_idx(valve)
    x = np.array([-2e-5, 1e-4, -8e-5, 1.0e7, 1.6e7, 0.0])  # Q_p<=0, P_a=1.6e7 > p_set
    eq_conservation, eq_supply, eq_relief = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9  # -2e-5 + 1e-4 - 8e-5 = 0
    assert abs(eq_supply - (-2e-5) / valve.q_ref) < 1e-12
    assert abs(eq_relief - (1.6e7 - 1.5e7) / valve.p_ref) < 1e-12


def test_relief_regime_residual_shrinks_to_near_zero_as_p_a_approaches_p_set():
    valve = make_relieving_valve(p_set=1.5e7)
    idx = make_relieving_idx(valve)
    x = np.array([0.0, 1e-4, -1e-4, 1.0e7, 1.5e7 + 1e-3, 0.0])  # P_a just barely above p_set
    _, _, eq_relief = valve.equations(x, idx)
    assert abs(eq_relief) < 1e-9


def test_relief_port_is_dead_when_not_in_closed_branch():
    """Outside the closed/relief branch (here: regulating, P_a == p_set,
    P_p above it), Q_T is a dead port -- pinned to zero, same 'dead port'
    pattern ReliefValve/CheckValve already use for their piloted Y port."""
    valve = make_relieving_valve(p_set=1.5e7)
    idx = make_relieving_idx(valve)
    x = np.array([1e-4, -1e-4, 3.0, 2.0e7, 1.5e7, 0.0])  # regulating regime, Q_t trial = 3.0
    _, _, eq_relief = valve.equations(x, idx)
    assert abs(eq_relief - 3.0 / valve.q_ref) < 1e-9  # not zero -- Q_t=3 isn't a root here


def test_initial_guess_seeds_t_flow_when_relieving():
    valve = make_relieving_valve(p_set=1.5e7)
    valve.anchors["P"].pressure = 3e7
    guess = valve.initial_guess
    assert guess[valve.flow_var_t] == 0.0
