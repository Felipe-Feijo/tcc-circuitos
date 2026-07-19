# tests/test_accumulator_hydraulic.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np


def make_accumulator(V0=1e-3, P0=3e6, Vf=0.0):
    from simulation.nodes.accumulator import Accumulator
    acc = Accumulator("acc", domain="hydraulic", properties={"V0": V0, "P0": P0})
    acc.Vf = Vf
    acc.add_anchor("P", domain="hydraulic")
    acc.anchors["P"].pressure_var = "P_P"
    acc.set_scale(p_ref=P0, q_ref=1e-4)
    return acc


def make_idx():
    return {"P_P": 0, "Q_acc": 1}  # Q_acc = flow_var de um acumulador com id "acc" (porta única, sem sufixo)


# ---------------------------------------------------------------------------
# Contrato -- V0/P0 obrigatórios
# ---------------------------------------------------------------------------

def test_missing_v0_raises_value_error():
    from simulation.nodes.accumulator import Accumulator
    with pytest.raises(ValueError):
        Accumulator("acc", domain="hydraulic", properties={"P0": 3e6})


def test_missing_p0_raises_value_error():
    from simulation.nodes.accumulator import Accumulator
    with pytest.raises(ValueError):
        Accumulator("acc", domain="hydraulic", properties={"V0": 1e-3})


def test_hydraulic_ports_and_variables():
    acc = make_accumulator()
    assert acc.hydraulic_ports() == {"P": acc.flow_var}
    assert set(acc.variables) == {"P_P", acc.flow_var}


def test_variables_no_keyerror_before_anchor_wired():
    """Verify that .variables doesn't raise KeyError when "P" anchor hasn't been
    added yet. This tests the defensive .get("P") pattern instead of direct
    dictionary access."""
    from simulation.nodes.accumulator import Accumulator
    acc = Accumulator("acc", domain="hydraulic", properties={"V0": 1e-3, "P0": 3e6})
    # Don't add anchor yet -- test that .variables is defensive
    variables = acc.variables  # Should not raise KeyError
    # Without anchor, only flow_var should be in variables list
    assert variables == [acc.flow_var]


# ---------------------------------------------------------------------------
# Lei de Boyle -- p_hint e equations()
# ---------------------------------------------------------------------------

def test_p_hint_at_vf_zero_equals_p0():
    acc = make_accumulator(V0=1e-3, P0=3e6, Vf=0.0)
    assert acc.p_hint == pytest.approx(3e6)


def test_p_hint_at_half_volume_matches_boyle_law():
    acc = make_accumulator(V0=1e-3, P0=3e6, Vf=0.5e-3)
    # P0*V0/(V0-Vf) = 3e6*1e-3 / (1e-3 - 0.5e-3) = 6e6
    assert acc.p_hint == pytest.approx(6e6)


def test_equations_root_is_p_equals_p_gas():
    acc = make_accumulator(V0=1e-3, P0=3e6, Vf=0.5e-3)
    idx = make_idx()
    x = np.array([6e6, 1e-4])  # P_P = P_gas(Vf=0.5e-3) = 6e6
    (residual,) = acc.equations(x, idx)
    assert abs(residual) < 1e-9


def test_equations_nonzero_residual_when_pressure_off_boyle_curve():
    acc = make_accumulator(V0=1e-3, P0=3e6, Vf=0.5e-3)
    idx = make_idx()
    x = np.array([1e6, 1e-4])  # bem longe de 6e6
    (residual,) = acc.equations(x, idx)
    assert abs(residual) > 1e-2


# ---------------------------------------------------------------------------
# Bounds -- só do lado vazio
# ---------------------------------------------------------------------------

def test_bounds_force_q_nonnegative_near_empty():
    acc = make_accumulator(V0=1e-3, Vf=0.0)
    lo, hi = acc.bounds[acc.flow_var]
    assert lo == 0.0
    assert hi is None


def test_bounds_empty_dict_away_from_empty():
    acc = make_accumulator(V0=1e-3, Vf=0.5e-3)
    assert acc.bounds == {}


def test_bounds_threshold_matches_v0_times_1em3():
    V0 = 1e-3
    EPS = V0 * 1e-3
    acc_at_eps = make_accumulator(V0=V0, Vf=EPS)
    acc_above_eps = make_accumulator(V0=V0, Vf=EPS * 1.1)
    assert acc_at_eps.bounds != {}
    assert acc_above_eps.bounds == {}


# ---------------------------------------------------------------------------
# post_step_update -- integração e clip defensivo
# ---------------------------------------------------------------------------

def test_post_step_integrates_vf_from_flow():
    acc = make_accumulator(V0=1e-3, Vf=0.2e-3)
    acc.anchors["P"].flow = 1e-4  # m^3/s entrando
    acc.post_step_update(dt=1.0)
    assert acc.Vf == pytest.approx(0.3e-3)


def test_post_step_clips_vf_at_v0():
    acc = make_accumulator(V0=1e-3, Vf=0.9e-3)
    acc.anchors["P"].flow = 1.0  # vazão absurda, estouraria V0 num passo só
    acc.post_step_update(dt=1.0)
    assert acc.Vf == pytest.approx(1e-3)


def test_post_step_clips_vf_at_zero():
    acc = make_accumulator(V0=1e-3, Vf=0.1e-3)
    acc.anchors["P"].flow = -1.0  # vazão absurda saindo
    acc.post_step_update(dt=1.0)
    assert acc.Vf == 0.0


def test_post_step_noop_when_dt_is_none():
    acc = make_accumulator(V0=1e-3, Vf=0.3e-3)
    acc.anchors["P"].flow = 1e-4
    acc.post_step_update(dt=None)
    assert acc.Vf == pytest.approx(0.3e-3)


def test_post_step_skips_integration_when_flow_is_string_placeholder():
    """anchor.flow pode ser uma string sentinela (não resolvida ainda) em
    alguns pontos do ciclo do solver -- mesma guarda usada em
    single_acting_cylinder.post_step_update."""
    acc = make_accumulator(V0=1e-3, Vf=0.3e-3)
    acc.anchors["P"].flow = "unresolved"
    acc.post_step_update(dt=1.0)
    assert acc.Vf == pytest.approx(0.3e-3)


# ---------------------------------------------------------------------------
# Estado visual e serialização
# ---------------------------------------------------------------------------

def test_get_visual_state_matches_vf_over_v0():
    acc = make_accumulator(V0=1e-3, Vf=0.25e-3)
    assert acc.get_visual_state() == pytest.approx(0.25)


def test_get_visual_state_clamped_to_unit_range():
    acc = make_accumulator(V0=1e-3, Vf=1e-3)
    assert acc.get_visual_state() == pytest.approx(1.0)


def test_get_state_and_set_state_roundtrip_vf():
    acc = make_accumulator(V0=1e-3, Vf=0.4e-3)
    state = acc.get_state()
    assert state["Vf"] == pytest.approx(0.4e-3)

    acc2 = make_accumulator(V0=1e-3, Vf=0.0)
    acc2.set_state(state)
    assert acc2.Vf == pytest.approx(0.4e-3)


# ---------------------------------------------------------------------------
# Ponta a ponta: bomba carregando o acumulador
# ---------------------------------------------------------------------------

def test_pump_charging_accumulator_end_to_end():
    """Bomba de deslocamento fixo empurrando fluido pra dentro do
    acumulador. run_until_stable(dt) resolve o sistema não-linear com o
    Vf ATUAL (aqui, 0.0 -- a pressão resolvida fica presa em
    P_gas(0)=P0) e só DEPOIS, dentro do mesmo call, roda
    post_step_update(dt) via compute_outputs -- então Vf já cresce a
    partir da vazão resolvida nesse mesmo run_until_stable."""
    from simulation.simulation_engine import SimulationEngine
    from simulation.nodes.accumulator import Accumulator
    from simulation.nodes.reservoir import Reservoir
    from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
    from simulation.connections import Connection

    pump = FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": 1e-4})
    pump.add_anchor("P", domain="hydraulic")
    pump.add_anchor("S", domain="hydraulic")

    res_suction = Reservoir("res_suction", domain="hydraulic", properties={"pressure": 0.0})
    res_suction.add_anchor("T", domain="hydraulic")

    acc = Accumulator("acc", domain="hydraulic", properties={"V0": 1e-3, "P0": 3e6})
    acc.add_anchor("P", domain="hydraulic")

    conn1 = Connection(pump.get_anchor("S"), res_suction.get_anchor("T"))
    conn2 = Connection(pump.get_anchor("P"), acc.get_anchor("P"))

    nodes = {"pump": pump, "res_suction": res_suction, "acc": acc}
    connections = {c.id: c for c in (conn1, conn2)}

    engine = SimulationEngine(nodes, connections)
    engine.run_until_stable(dt=1.0)

    acc_pressure = acc.get_anchor("P").pressure
    assert acc_pressure == pytest.approx(3e6, rel=1e-3)  # P_gas(Vf=0) = P0, resolvido antes do post_step_update
    assert acc.Vf > 0.0  # post_step_update já rodou dentro deste run_until_stable
