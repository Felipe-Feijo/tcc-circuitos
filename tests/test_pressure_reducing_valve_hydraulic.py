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
