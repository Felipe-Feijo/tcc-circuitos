import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np

from simulation.nodes.throttle_valve import ThrottleValve


def make_valve(k=1e-7):
    valve = ThrottleValve("tv", domain="hydraulic", properties={"k": k})
    valve.add_anchor("X", domain="hydraulic")
    valve.add_anchor("Y", domain="hydraulic")
    valve.anchors["X"].pressure_var = "P_X"
    valve.anchors["Y"].pressure_var = "P_Y"
    return valve


def make_idx():
    return {"Q_tv_X": 0, "Q_tv_Y": 1, "P_X": 2, "P_Y": 3}


# ---------------------------------------------------------------------------
# Contrato hidráulico -- ports/variables/k obrigatório
# ---------------------------------------------------------------------------

def test_missing_k_raises_value_error():
    with pytest.raises(ValueError):
        ThrottleValve("tv", domain="hydraulic", properties={})


def test_hydraulic_ports_and_variables():
    valve = make_valve()
    assert set(valve.hydraulic_ports().keys()) == {"X", "Y"}
    assert set(valve.variables) == {valve.flow_var_x, valve.flow_var_y, "P_X", "P_Y"}


# ---------------------------------------------------------------------------
# Equação -- orifício turbulento simétrico, sem ramificação
# ---------------------------------------------------------------------------

def test_conservation_equation_is_qx_plus_qy():
    valve = make_valve()
    idx = make_idx()
    x = np.array([-2e-4, 2e-4, 9e6, 5e6])
    eq_conservation, _ = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9


def test_orifice_equation_root_flow_x_to_y():
    """Fluxo entrando por X (Q_X>0), saindo por Y -- P_X > P_Y, ponto raiz
    calculado à mão: (P_X - P_Y) = (Q_X/k)^2."""
    k = 1e-7
    valve = make_valve(k=k)
    idx = make_idx()
    Q_x = 2e-4
    dp = (Q_x / k) ** 2  # = 4e8
    P_x, P_y = 5e6 + dp, 5e6
    x = np.array([Q_x, -Q_x, P_x, P_y])
    eq_conservation, eq_orifice = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_orifice) < 1e-6


def test_orifice_equation_root_flow_y_to_x():
    """Fluxo entrando por Y (Q_X<0), saindo por X -- P_Y > P_X, sinal
    oposto ao caso anterior (mesma equação, orifício é simétrico)."""
    k = 1e-7
    valve = make_valve(k=k)
    idx = make_idx()
    Q_x = -2e-4
    dp = -((Q_x / k) ** 2)  # negativo, copysign com Q_x<0
    P_x, P_y = 5e6 + dp, 5e6
    x = np.array([Q_x, -Q_x, P_x, P_y])
    eq_conservation, eq_orifice = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_orifice) < 1e-6


def test_wrong_sign_flow_is_not_a_root():
    """Sanity check: usar o dp do sentido X->Y com o Q_X do sentido
    oposto não deve satisfazer a equação."""
    k = 1e-7
    valve = make_valve(k=k)
    idx = make_idx()
    Q_x = -2e-4
    dp = (2e-4 / k) ** 2  # dp do sentido errado (positivo, mas Q_x é negativo)
    P_x, P_y = 5e6 + dp, 5e6
    x = np.array([Q_x, -Q_x, P_x, P_y])
    _, eq_orifice = valve.equations(x, idx)
    assert abs(eq_orifice) > 1e-3
