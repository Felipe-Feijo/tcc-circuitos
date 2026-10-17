import sys
import math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pytest

from simulation.nodes.pilot_operated_relief_valve import PilotOperatedReliefValve

P_SET = 1.0e7
P_VENT = 3.0e5
K = PilotOperatedReliefValve.K_ORIFICE


def make_valve(p_set=P_SET, p_vent=P_VENT):
    props = {"p_set": p_set}
    if p_vent is not None:
        props["p_vent"] = p_vent
    v = PilotOperatedReliefValve("po", domain="hydraulic", properties=props)
    for name in ("P", "T", "X"):
        v.add_anchor(name, domain="hydraulic")
        v.anchors[name].pressure_var = f"P_{name}"
    v.set_scale(P_SET, 1e-3)
    return v


def residuals(v, **values):
    idx = {name: i for i, name in enumerate(v.variables)}
    x = np.zeros(len(idx))
    for name, value in values.items():
        x[idx[name]] = value
    return v.equations(x, idx)


def state(v, *, q_p=0.0, q_t=0.0, q_x=0.0, q_main=0.0, q_pilot=0.0, p_p=0.0, p_t=0.0, p_x=0.0):
    return {
        v.flow_var_p: q_p, v.flow_var_t: q_t, v.flow_var_x: q_x,
        v.flow_var_main: q_main, v.flow_var_pilot: q_pilot,
        "P_P": p_p, "P_T": p_t, "P_X": p_x,
    }


def assert_root(eqs):
    assert len(eqs) == 5
    for e in eqs:
        assert abs(e) < 1e-9


# --- construction -----------------------------------------------------------

def test_node_type():
    assert make_valve().type == "pilot_operated_relief_valve"


def test_missing_p_set_raises():
    with pytest.raises(ValueError, match="p_set"):
        PilotOperatedReliefValve("po", domain="hydraulic", properties={})


@pytest.mark.parametrize("props", [{"p_set": 0.0}, {"p_set": -1.0}, {"p_set": 1e7, "p_vent": 0.0}, {"p_set": 1e7, "p_vent": -5.0}])
def test_non_positive_settings_raise(props):
    with pytest.raises(ValueError):
        PilotOperatedReliefValve("po", domain="hydraulic", properties=props)


def test_p_vent_defaults_when_missing():
    v = make_valve(p_vent=None)
    assert v.p_vent == PilotOperatedReliefValve.DEFAULT_P_VENT == 3e5


def test_p_hint_is_system_pressure():
    assert make_valve().p_hint == P_SET + P_VENT


# --- ports / variables / bounds --------------------------------------------

def test_x_is_a_flow_port_not_a_dead_port():
    v = make_valve()
    assert set(v.hydraulic_ports()) == {"P", "T", "X"}
    assert v.hydraulic_ports()["X"] == v.flow_var_x
    assert not hasattr(v, "dead_ports") or v.dead_ports() == []


def test_variables():
    v = make_valve()
    assert set(v.variables) == {
        v.flow_var_p, v.flow_var_t, v.flow_var_x, v.flow_var_main, v.flow_var_pilot,
        "P_P", "P_T", "P_X",
    }


def test_bounds():
    v = make_valve()
    assert v.bounds == {
        v.flow_var_p: (0.0, None),
        v.flow_var_t: (None, 0.0),
        v.flow_var_main: (0.0, None),
        v.flow_var_pilot: (0.0, None),
    }


# --- exact roots per regime ------------------------------------------------

def test_closed_regime_is_root():
    v = make_valve()
    assert_root(residuals(v, **state(v, p_p=5e6, p_x=5e6)))


def test_regulating_regime_is_root():
    v = make_valve()
    q = 1e-3
    q_orif = K * math.sqrt(P_VENT)
    assert_root(residuals(v, **state(
        v, q_p=q, q_t=-q, q_main=q - q_orif, q_pilot=q_orif,
        p_p=P_SET + P_VENT, p_x=P_SET,
    )))


def test_vented_regime_is_root():
    v = make_valve()
    q = 1e-3
    q_orif = K * math.sqrt(P_VENT)
    assert_root(residuals(v, **state(
        v, q_p=q, q_t=-(q - q_orif), q_x=-q_orif, q_main=q - q_orif,
        p_p=P_VENT, p_x=0.0,
    )))


def test_pilot_only_regime_is_root():
    v = make_valve()
    q = 0.5 * K * math.sqrt(P_VENT)
    assert_root(residuals(v, **state(
        v, q_p=q, q_t=-q, q_pilot=q,
        p_p=P_SET + (q / K) ** 2, p_x=P_SET,
    )))


def test_regulating_pressure_off_target_is_not_root():
    v = make_valve()
    q = 1e-3
    q_orif = K * math.sqrt(P_VENT)
    eqs = residuals(v, **state(
        v, q_p=q, q_t=-q, q_main=q - q_orif, q_pilot=q_orif,
        p_p=P_SET, p_x=P_SET - P_VENT,
    ))
    assert max(abs(e) for e in eqs) > 1e-6


def test_passive_regime_when_t_backpressured():
    # T above p_set: pilot stage is passive (P_X = P_T), main stage
    # regulates on top of it -> P_P = P_T + p_vent.
    v = make_valve()
    p_back = 2.0e7
    q = 1e-3
    q_orif = K * math.sqrt(P_VENT)
    eqs = residuals(v, **state(
        v, q_p=q, q_t=-q, q_main=q - q_orif, q_pilot=q_orif,
        p_p=p_back + P_VENT, p_x=p_back, p_t=p_back,
    ))
    assert all(math.isfinite(e) for e in eqs)
    assert_root(eqs)


def test_registered_in_simulate_json():
    from tests.simulate_json import ANCHORS_BY_TYPE, _get_node_classes
    assert _get_node_classes()["PilotOperatedReliefValve"] is PilotOperatedReliefValve
    assert ANCHORS_BY_TYPE["PilotOperatedReliefValve"] == ["P", "T", "X"]
