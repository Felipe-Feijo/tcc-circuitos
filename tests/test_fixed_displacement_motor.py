import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np

from simulation.nodes.fixed_displacement_motor import FixedDisplacementMotor


def make_motor(D=1.5e-6, control_mode="torque", T_load=50.0, omega_target=100.0):
    props = {"D": D, "control_mode": control_mode}
    if control_mode == "torque":
        props["T_load"] = T_load
    else:
        props["omega_target"] = omega_target
    motor = FixedDisplacementMotor("m1", domain="hydraulic", properties=props)
    motor.add_anchor("A", domain="hydraulic")
    motor.add_anchor("B", domain="hydraulic")
    motor.anchors["A"].pressure_var = "P_A"
    motor.anchors["B"].pressure_var = "P_B"
    return motor


# ---------------------------------------------------------------------------
# Contrato / validação de propriedades
# ---------------------------------------------------------------------------

def test_missing_d_raises_value_error():
    with pytest.raises(ValueError):
        FixedDisplacementMotor("m1", domain="hydraulic", properties={"control_mode": "torque", "T_load": 50.0})


def test_invalid_control_mode_raises_value_error():
    with pytest.raises(ValueError):
        FixedDisplacementMotor("m1", domain="hydraulic", properties={"D": 1e-6, "control_mode": "bogus"})


def test_missing_t_load_in_torque_mode_raises_value_error():
    with pytest.raises(ValueError):
        FixedDisplacementMotor("m1", domain="hydraulic", properties={"D": 1e-6, "control_mode": "torque"})


def test_missing_omega_target_in_speed_mode_raises_value_error():
    with pytest.raises(ValueError):
        FixedDisplacementMotor("m1", domain="hydraulic", properties={"D": 1e-6, "control_mode": "speed"})


def test_hydraulic_ports_and_variables():
    motor = make_motor()
    assert motor.hydraulic_ports() == {"A": motor.flow_var_a, "B": motor.flow_var_b}
    assert set(motor.variables) == {motor.flow_var_a, motor.flow_var_b, "P_A", "P_B"}


def test_is_flow_source():
    assert make_motor().is_flow_source is True


# ---------------------------------------------------------------------------
# Modo torque -- Δp = T_load/D, sem depender do sinal de Q
# ---------------------------------------------------------------------------

def test_torque_mode_exact_root_forward():
    D, T_load = 1.5e-6, 50.0
    motor = make_motor(D=D, control_mode="torque", T_load=T_load)
    idx = {motor.flow_var_a: 0, motor.flow_var_b: 1, "P_A": 2, "P_B": 3}

    delta_p = T_load / D
    x = np.array([2e-4, -2e-4, delta_p, 0.0])
    eq_conservation, eq_mode = motor.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_mode) < 1e-6


def test_torque_mode_root_independent_of_flow_direction():
    """Reversão de sentido não é caso especial: a mesma Δp continua sendo
    raiz da equação de torque mesmo com Q_A negativo (fluxo revertido
    pelo resto do circuito)."""
    D, T_load = 1.5e-6, 50.0
    motor = make_motor(D=D, control_mode="torque", T_load=T_load)
    idx = {motor.flow_var_a: 0, motor.flow_var_b: 1, "P_A": 2, "P_B": 3}

    delta_p = T_load / D
    x = np.array([-3e-4, 3e-4, delta_p, 0.0])  # Q_A negativo -- sentido revertido
    eq_conservation, eq_mode = motor.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_mode) < 1e-6  # ainda raiz -- a equação nunca olhou pro sinal de Q


def test_torque_mode_wrong_delta_p_is_not_a_root():
    D, T_load = 1.5e-6, 50.0
    motor = make_motor(D=D, control_mode="torque", T_load=T_load)
    idx = {motor.flow_var_a: 0, motor.flow_var_b: 1, "P_A": 2, "P_B": 3}

    x = np.array([2e-4, -2e-4, 0.0, 0.0])  # delta_p=0, deveria ser T_load/D
    _, eq_mode = motor.equations(x, idx)
    assert abs(eq_mode) > 1e-3


# ---------------------------------------------------------------------------
# Modo speed -- Q_A = D * omega_target
# ---------------------------------------------------------------------------

def test_speed_mode_exact_root():
    D, omega_target = 1.5e-6, 100.0
    motor = make_motor(D=D, control_mode="speed", omega_target=omega_target)
    idx = {motor.flow_var_a: 0, motor.flow_var_b: 1, "P_A": 2, "P_B": 3}

    q_a = D * omega_target
    x = np.array([q_a, -q_a, 5e5, 1e5])  # pressões arbitrárias -- não entram na eq. speed
    eq_conservation, eq_mode = motor.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_mode) < 1e-9


def test_speed_mode_negative_target_reverses_flow():
    D, omega_target = 1.5e-6, -100.0  # sentido revertido comandado
    motor = make_motor(D=D, control_mode="speed", omega_target=omega_target)
    idx = {motor.flow_var_a: 0, motor.flow_var_b: 1, "P_A": 2, "P_B": 3}

    q_a = D * omega_target  # negativo
    x = np.array([q_a, -q_a, 0.0, 0.0])
    eq_conservation, eq_mode = motor.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_mode) < 1e-9


# ---------------------------------------------------------------------------
# Ponta a ponta
# ---------------------------------------------------------------------------

def test_end_to_end_torque_mode_between_two_reservoirs():
    from simulation.hydraulic.solver import NonlinearSystemSolver, NodeContinuity
    from simulation.hydraulic.scale_context import ScaleContext
    from simulation.nodes.reservoir import Reservoir

    D, T_load = 1.5e-6, 50.0
    delta_p_expected = T_load / D
    motor = make_motor(D=D, control_mode="torque", T_load=T_load)

    res_a = Reservoir("res_a", domain="hydraulic", properties={"pressure": delta_p_expected})
    res_a.add_anchor("T", domain="hydraulic")
    res_b = Reservoir("res_b", domain="hydraulic", properties={"pressure": 0.0})
    res_b.add_anchor("T", domain="hydraulic")

    motor.anchors["A"].pressure_var = res_a.anchors["T"].pressure_var = "P_A"
    motor.anchors["B"].pressure_var = res_b.anchors["T"].pressure_var = "P_B"

    ctx = ScaleContext(p_ref=max(delta_p_expected, 1e5), q_ref=1e-4, zc=1e12)
    cont_a = NodeContinuity("P_A", [motor.flow_var_a, res_a.flow_var])
    cont_b = NodeContinuity("P_B", [motor.flow_var_b, res_b.flow_var])
    cont_a.apply_context(ctx)
    cont_b.apply_context(ctx)

    solver = NonlinearSystemSolver([motor, res_a, res_b, cont_a, cont_b])
    sol = solver.solve(
        {motor.flow_var_a: 1e-4, motor.flow_var_b: -1e-4,
         "P_A": delta_p_expected, "P_B": 0.0},
        ctx,
    )

    assert abs(sol["P_A"] - sol["P_B"] - delta_p_expected) < delta_p_expected * 1e-3
    assert abs(sol[motor.flow_var_a] + sol[motor.flow_var_b]) < 1e-9


def test_end_to_end_speed_mode_forces_flow_between_two_reservoirs():
    from simulation.hydraulic.solver import NonlinearSystemSolver, NodeContinuity
    from simulation.hydraulic.scale_context import ScaleContext
    from simulation.nodes.reservoir import Reservoir

    D, omega_target = 1.5e-6, 100.0
    q_expected = D * omega_target
    motor = make_motor(D=D, control_mode="speed", omega_target=omega_target)

    res_a = Reservoir("res_a", domain="hydraulic", properties={"pressure": 3e5})
    res_a.add_anchor("T", domain="hydraulic")
    res_b = Reservoir("res_b", domain="hydraulic", properties={"pressure": 0.0})
    res_b.add_anchor("T", domain="hydraulic")

    motor.anchors["A"].pressure_var = res_a.anchors["T"].pressure_var = "P_A"
    motor.anchors["B"].pressure_var = res_b.anchors["T"].pressure_var = "P_B"

    ctx = ScaleContext(p_ref=3e5, q_ref=max(q_expected, 1e-10), zc=1e12)
    cont_a = NodeContinuity("P_A", [motor.flow_var_a, res_a.flow_var])
    cont_b = NodeContinuity("P_B", [motor.flow_var_b, res_b.flow_var])
    cont_a.apply_context(ctx)
    cont_b.apply_context(ctx)

    solver = NonlinearSystemSolver([motor, res_a, res_b, cont_a, cont_b])
    sol = solver.solve(
        {motor.flow_var_a: q_expected, motor.flow_var_b: -q_expected,
         "P_A": 3e5, "P_B": 0.0},
        ctx,
    )

    assert abs(sol[motor.flow_var_a] - q_expected) < abs(q_expected) * 1e-3
