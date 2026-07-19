import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import math
import pytest
import numpy as np

from simulation.nodes.pumps.centrifugal_pump import CentrifugalPump


def make_pump(h_shutoff=2e6, q_max=1e-3):
    pump = CentrifugalPump("cp", domain="hydraulic", properties={
        "H_shutoff": h_shutoff, "Q_max": q_max,
    })
    pump.add_anchor("P", domain="hydraulic")
    pump.add_anchor("S", domain="hydraulic")
    pump.anchors["P"].pressure_var = "P_P"
    pump.anchors["S"].pressure_var = "P_S"
    return pump


# ---------------------------------------------------------------------------
# Contrato
# ---------------------------------------------------------------------------

def test_missing_h_shutoff_raises_value_error():
    with pytest.raises(ValueError):
        CentrifugalPump("cp", domain="hydraulic", properties={"Q_max": 1e-3})


def test_missing_q_max_raises_value_error():
    with pytest.raises(ValueError):
        CentrifugalPump("cp", domain="hydraulic", properties={"H_shutoff": 2e6})


def test_is_flow_source_and_hints():
    pump = make_pump(h_shutoff=2e6, q_max=1e-3)
    assert pump.is_flow_source is True
    assert pump.flow_hint == 1e-3
    assert pump.p_hint == 2e6


def test_hydraulic_ports_and_variables():
    pump = make_pump()
    assert pump.hydraulic_ports() == {"P": pump.flow_var_p, "S": pump.flow_var_s}
    assert set(pump.variables) == {pump.flow_var_p, pump.flow_var_s}


# ---------------------------------------------------------------------------
# Curva característica -- sem ramificação, pontos exatos
# ---------------------------------------------------------------------------

def test_shutoff_point_q_zero_gives_delta_p_equals_h_shutoff():
    h_shutoff, q_max = 2e6, 1e-3
    pump = make_pump(h_shutoff, q_max)
    idx = {pump.flow_var_p: 0, pump.flow_var_s: 1, "P_P": 2, "P_S": 3}
    x = np.array([0.0, 0.0, h_shutoff, 0.0])  # Q_s=0, delta_p=H_shutoff

    eq_conservation, eq_curve = pump.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_curve) < 1e-9


def test_free_flow_point_q_max_gives_zero_delta_p():
    h_shutoff, q_max = 2e6, 1e-3
    pump = make_pump(h_shutoff, q_max)
    idx = {pump.flow_var_p: 0, pump.flow_var_s: 1, "P_P": 2, "P_S": 3}
    x = np.array([-q_max, q_max, 0.0, 0.0])  # Q_s=Q_max, delta_p=0

    eq_conservation, eq_curve = pump.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_curve) < 1e-9


def test_intermediate_point_matches_curve_formula():
    h_shutoff, q_max = 2e6, 1e-3
    pump = make_pump(h_shutoff, q_max)
    idx = {pump.flow_var_p: 0, pump.flow_var_s: 1, "P_P": 2, "P_S": 3}

    Q_s = q_max / 2
    delta_p = h_shutoff * (1 - (Q_s / q_max) ** 2)
    x = np.array([-Q_s, Q_s, delta_p, 0.0])

    eq_conservation, eq_curve = pump.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_curve) < 1e-6


def test_wrong_delta_p_is_not_a_root():
    h_shutoff, q_max = 2e6, 1e-3
    pump = make_pump(h_shutoff, q_max)
    idx = {pump.flow_var_p: 0, pump.flow_var_s: 1, "P_P": 2, "P_S": 3}

    Q_s = q_max / 2
    x = np.array([-Q_s, Q_s, h_shutoff, 0.0])  # delta_p errado (deveria ser 0.75*H)

    _, eq_curve = pump.equations(x, idx)
    assert abs(eq_curve) > 1e-3


# ---------------------------------------------------------------------------
# Ponta a ponta
# ---------------------------------------------------------------------------

def test_end_to_end_pump_between_two_reservoirs():
    from simulation.hydraulic.solver import NonlinearSystemSolver, NodeContinuity
    from simulation.hydraulic.scale_context import ScaleContext
    from simulation.nodes.reservoir import Reservoir

    h_shutoff, q_max = 2e6, 1e-3
    pump = make_pump(h_shutoff, q_max)

    res_p = Reservoir("res_p", domain="hydraulic", properties={"pressure": h_shutoff / 2})
    res_p.add_anchor("T", domain="hydraulic")
    res_s = Reservoir("res_s", domain="hydraulic", properties={"pressure": 0.0})
    res_s.add_anchor("T", domain="hydraulic")

    pump.anchors["P"].pressure_var = res_p.anchors["T"].pressure_var = "P_P"
    pump.anchors["S"].pressure_var = res_s.anchors["T"].pressure_var = "P_S"

    ctx = ScaleContext(p_ref=h_shutoff, q_ref=q_max, zc=1e12)
    cont_p = NodeContinuity("P_P", [pump.flow_var_p, res_p.flow_var])
    cont_s = NodeContinuity("P_S", [pump.flow_var_s, res_s.flow_var])
    cont_p.apply_context(ctx)
    cont_s.apply_context(ctx)

    solver = NonlinearSystemSolver([pump, res_p, res_s, cont_p, cont_s])
    sol = solver.solve(
        {pump.flow_var_p: -q_max / 2, pump.flow_var_s: q_max / 2,
         "P_P": h_shutoff / 2, "P_S": 0.0},
        ctx,
    )

    expected_q_s = q_max / math.sqrt(2)  # H/2 = H*(1-(Q/Qmax)^2) -> Q=Qmax/sqrt(2)
    assert abs(sol[pump.flow_var_s] - expected_q_s) < expected_q_s * 1e-3
    assert abs(sol[pump.flow_var_p] + sol[pump.flow_var_s]) < 1e-9


def test_end_to_end_backpressure_beyond_shutoff_clamps_to_zero_flow():
    """Regressão do bug relatado: contrapressão acima de H_shutoff não tem
    raiz real na parábola -- sem os bounds, o solver escorregava pra
    vazão negativa. Com Q_S travado em [0, Q_max], o ponto mais próximo
    alcançável é vazão zero, não negativa."""
    from simulation.hydraulic.solver import NonlinearSystemSolver, NodeContinuity
    from simulation.hydraulic.scale_context import ScaleContext
    from simulation.nodes.reservoir import Reservoir

    h_shutoff, q_max = 2e6, 1e-3
    pump = make_pump(h_shutoff, q_max)

    # Contrapressão 50% acima do shutoff -- além do que a bomba consegue vencer.
    res_p = Reservoir("res_p", domain="hydraulic", properties={"pressure": h_shutoff * 1.5})
    res_p.add_anchor("T", domain="hydraulic")
    res_s = Reservoir("res_s", domain="hydraulic", properties={"pressure": 0.0})
    res_s.add_anchor("T", domain="hydraulic")

    pump.anchors["P"].pressure_var = res_p.anchors["T"].pressure_var = "P_P"
    pump.anchors["S"].pressure_var = res_s.anchors["T"].pressure_var = "P_S"

    ctx = ScaleContext(p_ref=h_shutoff, q_ref=q_max, zc=1e12)
    cont_p = NodeContinuity("P_P", [pump.flow_var_p, res_p.flow_var])
    cont_s = NodeContinuity("P_S", [pump.flow_var_s, res_s.flow_var])
    cont_p.apply_context(ctx)
    cont_s.apply_context(ctx)

    solver = NonlinearSystemSolver([pump, res_p, res_s, cont_p, cont_s])
    sol = solver.solve(
        {pump.flow_var_p: -q_max / 2, pump.flow_var_s: q_max / 2,
         "P_P": h_shutoff * 1.5, "P_S": 0.0},
        ctx,
    )

    assert sol[pump.flow_var_s] >= -1e-9  # nunca negativa
    assert sol[pump.flow_var_s] < q_max * 1e-3  # praticamente zero
