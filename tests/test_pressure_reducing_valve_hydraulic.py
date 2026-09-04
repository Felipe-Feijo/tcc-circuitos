import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import math
import numpy as np
import pytest

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
# relieving=False (2-port, unchanged from the shipped base valve)
# ---------------------------------------------------------------------------
# These pin down that the relieving=True rewrite did not disturb the
# already-shipped 2-port path -- byte-for-byte the same three regimes
# (fully open / regulating / closed) as what's merged on main.

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


def test_closed_regime_is_exact_root_when_outlet_exceeds_setpoint_with_no_flow():
    """P_A pushed above p_set externally, Q_p already at its zero lower
    bound -- the valve should hold Q_p=0 rather than have no root."""
    valve = make_valve(p_set=1.5e7)
    idx = make_idx(valve)
    x = np.array([0.0, 0.0, 1.0e7, 1.6e7])  # P_p < P_a, P_a > p_set, Q_p=0
    eq_conservation, eq_fb = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_fb) < 1e-9


def test_conservation_residual_scales_with_imbalance():
    valve = make_valve(p_set=1.5e7)
    idx = make_idx(valve)
    x = np.array([5e-4, -1e-4, 1.0e7, 1.0e7])  # Q_P + Q_A = 4e-4, not conserved
    eq_conservation, _ = valve.equations(x, idx)
    assert abs(eq_conservation - 4e-4 / valve.q_ref) < 1e-12


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
# relieving=True: T port, 3-port conservation
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


def test_bounds_keep_a_forward_only_even_when_relieving():
    """Unlike an earlier design, A stays <= 0 (forward/outgoing) even when
    relieving -- this valve diverts excess supply to T without ever
    needing flow to reverse through A. See the module docstring's Scope
    note for why true external backfeed into A is out of scope."""
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


def test_initial_guess_seeds_t_flow_when_relieving():
    valve = make_relieving_valve(p_set=1.5e7)
    valve.anchors["P"].pressure = 3e7
    guess = valve.initial_guess
    assert guess[valve.flow_var_t] == 0.0


# ---------------------------------------------------------------------------
# relieving=True: dual Fischer-Burmeister physics
#
# These reproduce the exact tuning constants from equations() (kept in
# sync by comment -- if you change PENALTY_WEIGHT/SUPPLY_RIDGE_WEIGHT/
# RIDGE_WEIGHT there, update them here too). Their purpose is to pin the
# STRUCTURE of the formula (which terms exist, what they depend on), not
# to be the primary confidence check for end-to-end correctness -- that's
# what the SimulationEngine test at the bottom of this file is for.
# ---------------------------------------------------------------------------

_PENALTY_WEIGHT = 500.0
_SUPPLY_RIDGE_WEIGHT = 2.0
_RIDGE_WEIGHT = 0.0002


def test_fully_open_regime_is_exact_root_when_relieving():
    """Same fully-open regime as the 2-port valve (P_A=P_P, below p_set),
    now with T present but idle -- both ridge/penalty terms vanish at
    this point (Q_p>0, P_p==p_set*0+... below p_set so tanh term is
    negative but small; assert via direct equation call, not by hand)."""
    valve = make_relieving_valve(p_set=1.5e7)
    idx = make_relieving_idx(valve)
    # P_p == P_a == 1e7 (well below p_set), Q_t = 0 (idle).
    x = np.array([1e-4, -1e-4, 0.0, 1.0e7, 1.0e7, 0.0])
    eq_conservation, eq_supply, eq_relief = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    # eq_relief: a = (p_set-P_a)/P_scale > 0, b_relief = -Q_t/Q_scale = 0
    # -- FB(a,0) = a - a = 0 exactly, plus the ridge (0) -- dead port root.
    assert abs(eq_relief) < 1e-9
    # eq_supply's FB part is 0 (b_supply=0 branch); the two correction
    # terms are small but not exactly 0 (P_p < p_set here), so just check
    # it's small relative to the scale, not exactly zero.
    assert abs(eq_supply) < 0.1


def test_reverse_flow_penalty_grows_as_q_p_goes_negative():
    """The penalty term added to eq_supply must strictly increase in
    magnitude as Q_p goes more negative -- this is what excludes the
    reverse-flow-through-P root at the equation level, not just via
    `bounds` (which fsolve's own unbounded stage ignores)."""
    valve = make_relieving_valve(p_set=1.5e7)
    idx = make_relieving_idx(valve)

    def eq_supply_at(q_p):
        x = np.array([q_p, -1e-4 - q_p, 0.0, 2.0e7, 1.5e7, 0.0])
        _, eq_supply, _ = valve.equations(x, idx)
        return eq_supply

    residual_at_zero = eq_supply_at(0.0)
    residual_at_small_negative = eq_supply_at(-1e-6)
    residual_at_large_negative = eq_supply_at(-1e-4)
    assert abs(residual_at_small_negative) > abs(residual_at_zero)
    assert abs(residual_at_large_negative) > abs(residual_at_small_negative)


def test_relief_tie_break_pulls_q_t_toward_zero_when_not_needed():
    """At the shared root (P_a=p_set, P_p>=p_set), Q_t=0 must have a
    strictly smaller |eq_relief| residual than some nonzero Q_t -- the
    ridge is what breaks the otherwise rank-deficient tie in favor of
    'relief idle unless genuinely needed'."""
    valve = make_relieving_valve(p_set=1.5e7)
    idx = make_relieving_idx(valve)

    def eq_relief_at(q_t):
        x = np.array([1e-4, -1e-4 - q_t, q_t, 2.0e7, 1.5e7, 0.0])
        _, _, eq_relief = valve.equations(x, idx)
        return eq_relief

    assert abs(eq_relief_at(0.0)) < abs(eq_relief_at(-1e-5))


def test_relief_engages_when_p_a_pushed_above_p_set_externally():
    """With Q_p pinned at 0 (supply can't help) and P_a pushed above
    p_set, eq_relief's magnitude must shrink as Q_t moves toward the
    value conservation implies is needed (-Q_a), confirming the relief
    FB is actually sensitive to Q_t in this regime (not a dead port)."""
    valve = make_relieving_valve(p_set=1.5e7)
    idx = make_relieving_idx(valve)

    def eq_relief_at(q_t):
        x = np.array([0.0, 1e-4, q_t, 1.0e7, 1.6e7, 0.0])
        _, _, eq_relief = valve.equations(x, idx)
        return eq_relief

    # Q_t=0 (no relief at all) should be far worse than Q_t=-1e-4
    # (matches conservation: Q_p=0, Q_a=1e-4, needs Q_t=-1e-4).
    assert abs(eq_relief_at(-1e-4)) < abs(eq_relief_at(0.0))


# ---------------------------------------------------------------------------
# End-to-end: relief regime through the real SimulationEngine.
#
# This is the regression test for the bug this whole redesign fixed: an
# earlier hard-branch design pinned Q_p to exactly zero once P_a exceeded
# p_set, which directly contradicted any upstream flow SOURCE that
# forces its own nonzero Q_p (e.g. a fixed-displacement pump) -- the
# shared pressure diverged instead of converging. See
# docs/superpowers/specs/2026-09-03-pressure-reducing-valve-relief-port-design.md
# for the full history (including a first relief-port attempt that also
# needed reverse flow through A -- that scenario is now explicitly out
# of scope, see the module docstring's Scope note).
# ---------------------------------------------------------------------------

def test_relief_regime_diverts_excess_supply_pump_flow_to_tank_end_to_end():
    """A fixed-displacement pump forces more flow into P (1e-2 m3/s) than
    a much smaller downstream load can accept (2e-4 m3/s, modeled the
    same way -- a second fixed-displacement pump's suction tied to A, so
    its OWN flow demand is fixed regardless of pressure). The valve must
    hold P_A near p_set by diverting the difference to T, without ever
    reversing flow through A. Runs the real SimulationEngine, not
    equations() in isolation."""
    from simulation.simulation_engine import SimulationEngine
    from simulation.nodes.reservoir import Reservoir
    from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
    from simulation.connections import Connection

    p_set = 2.0e6

    prv = PressureReducingValve("prv", domain="hydraulic", properties={"p_set": p_set, "relieving": True})
    prv.add_anchor("P", domain="hydraulic")
    prv.add_anchor("A", domain="hydraulic")
    prv.add_anchor("T", domain="hydraulic")

    supply_pump = FixedDisplacementPump("supply_pump", domain="hydraulic", properties={"Q": 1e-2})
    supply_pump.add_anchor("P", domain="hydraulic")
    supply_pump.add_anchor("S", domain="hydraulic")
    res_supply_suction = Reservoir("res_supply_suction", domain="hydraulic", properties={"pressure": 0.0})
    res_supply_suction.add_anchor("T", domain="hydraulic")

    res_tank = Reservoir("res_tank", domain="hydraulic", properties={"pressure": 0.0})
    res_tank.add_anchor("T", domain="hydraulic")

    load = FixedDisplacementPump("load", domain="hydraulic", properties={"Q": 2e-4})
    load.add_anchor("P", domain="hydraulic")
    load.add_anchor("S", domain="hydraulic")
    res_load_discharge = Reservoir("res_load_discharge", domain="hydraulic", properties={"pressure": 0.0})
    res_load_discharge.add_anchor("T", domain="hydraulic")

    conn_supply = Connection(supply_pump.get_anchor("P"), prv.get_anchor("P"))
    conn_supply_suction = Connection(supply_pump.get_anchor("S"), res_supply_suction.get_anchor("T"))
    conn_t = Connection(prv.get_anchor("T"), res_tank.get_anchor("T"))
    conn_load = Connection(prv.get_anchor("A"), load.get_anchor("S"))
    conn_load_discharge = Connection(load.get_anchor("P"), res_load_discharge.get_anchor("T"))

    nodes = {
        "prv": prv, "supply_pump": supply_pump, "res_supply_suction": res_supply_suction,
        "res_tank": res_tank, "load": load, "res_load_discharge": res_load_discharge,
    }
    connections = {
        c.id: c for c in (conn_supply, conn_supply_suction, conn_t, conn_load, conn_load_discharge)
    }

    engine = SimulationEngine(nodes, connections)
    engine.run_until_stable(dt=1.0)

    p_a = prv.get_anchor("A").pressure
    q_a = prv.get_anchor("A").flow
    q_t = prv.get_anchor("T").flow

    assert p_a == pytest.approx(p_set, rel=0.1)  # held near setpoint (ridge trade-off, see spec)
    assert q_a == pytest.approx(-2e-4, rel=1e-2)  # load's own fixed demand, unreversed
    assert q_t < -9e-3  # the vast majority of supply_pump's 1e-2 diverted to tank
