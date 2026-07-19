import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np

from simulation.nodes.check_valve.throttle_check_valve import ThrottleCheckValve


def make_valve(k=1e-7):
    valve = ThrottleCheckValve("tcv", domain="hydraulic", properties={"k": k})
    valve.add_anchor("X", domain="hydraulic")
    valve.add_anchor("Y", domain="hydraulic")
    valve.anchors["X"].pressure_var = "P_X"
    valve.anchors["Y"].pressure_var = "P_Y"
    return valve


def make_idx():
    return {"Q_tcv_X": 0, "Q_tcv_Y": 1, "P_X": 2, "P_Y": 3}


# ---------------------------------------------------------------------------
# Contrato hidráulico -- ports/variables/k obrigatório
# ---------------------------------------------------------------------------

def test_missing_k_raises_value_error_for_hydraulic_domain():
    with pytest.raises(ValueError):
        ThrottleCheckValve("tcv", domain="hydraulic", properties={})


def test_pneumatic_domain_does_not_require_k():
    valve = ThrottleCheckValve("tcv", domain="pneumatic", properties={})
    assert valve.variables == []


def test_hydraulic_ports_and_variables():
    valve = make_valve()
    assert set(valve.hydraulic_ports().keys()) == {"X", "Y"}
    assert set(valve.variables) == {valve.flow_var_x, valve.flow_var_y, "P_X", "P_Y"}


def test_pneumatic_domain_has_no_hydraulic_contract():
    valve = ThrottleCheckValve("tcv", domain="pneumatic", properties={})
    valve.add_anchor("X", domain="pneumatic")
    valve.add_anchor("Y", domain="pneumatic")
    assert valve.hydraulic_ports() == {}
    assert valve.variables == []


# ---------------------------------------------------------------------------
# Equação -- ramo favorável (resistência zero) vs ramo restrito (orifício)
# ---------------------------------------------------------------------------

def test_conservation_equation_is_qx_plus_qy():
    valve = make_valve()
    idx = make_idx()
    x = np.array([-1e-4, 1e-4, 3e6, 3e6])
    eq_conservation, _ = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9


def test_favorable_direction_is_zero_resistance_root():
    """P_Y >= P_X (sentido favorável, b<=0) -- resistência zero, P_X=P_Y
    é raiz exata, qualquer que seja a vazão."""
    valve = make_valve()
    idx = make_idx()
    x = np.array([-1e-4, 1e-4, 3e6, 3e6])  # P_X == P_Y
    _, eq_valve = valve.equations(x, idx)
    assert abs(eq_valve) < 1e-9


def test_restricted_direction_follows_orifice_equation():
    """P_X > P_Y (sentido restrito, b>0) -- não bloqueia, passa pelo
    orifício: b = copysign((Q_Y/k)^2, -Q_Y). Usa um ponto que é raiz
    exata dessa equação (calculado à mão) pra verificar o sinal certo."""
    k = 1e-7
    valve = make_valve(k=k)
    idx = make_idx()
    Q_y = -2e-4  # fluxo saindo por Y (sentido restrito, entra por X)
    b = (Q_y / k) ** 2  # = 4e6, com sinal + já que -Q_y > 0
    P_x, P_y = 9e6, 9e6 - b
    x = np.array([2e-4, Q_y, P_x, P_y])
    eq_conservation, eq_valve = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_valve) < 1e-6


def test_wrong_sign_flow_is_not_a_root_in_restricted_direction():
    """Sanity check: Q_Y positivo seleciona o ramo favorável (a
    ramificação é por sinal de Q_Y, não de P_X-P_Y -- ver docstring do
    módulo), então P_X=9e6 != P_Y não deveria satisfazer esse ramo."""
    k = 1e-7
    valve = make_valve(k=k)
    idx = make_idx()
    Q_y = 2e-4  # sinal errado pro sentido restrito
    b = (Q_y / k) ** 2
    P_x, P_y = 9e6, 9e6 - b
    x = np.array([-2e-4, Q_y, P_x, P_y])
    _, eq_valve = valve.equations(x, idx)
    assert abs(eq_valve) > 1e-3


# ---------------------------------------------------------------------------
# Visual state
# ---------------------------------------------------------------------------

def test_spurious_zero_pressure_root_is_rejected_for_restricted_flow():
    """Regressão do bug real: com a ramificação antiga (por P_X-P_Y), o
    solver encontrava P_X=P_Y=0 como raiz mesmo com Q_Y no sentido
    restrito (forçado de fora, ex: por uma bomba) -- porque o ramo
    favorável nunca menciona Q_Y. Isso não pode mais ser uma raiz."""
    k = 1e-7
    valve = make_valve(k=k)
    idx = make_idx()
    Q_y = -1e-4  # sentido restrito, forçado de fora
    x = np.array([1e-4, Q_y, 0.0, 0.0])  # P_X = P_Y = 0 -- raiz espúria antiga
    _, eq_valve = valve.equations(x, idx)
    assert abs(eq_valve) > 1e-3


def test_visual_state_open_when_favorable():
    valve = make_valve()
    valve.anchors["X"].pressure = 3e6
    valve.anchors["Y"].pressure = 5e6  # P_Y > P_X -- favorável
    assert valve.get_visual_state() == "open"


def test_visual_state_closed_when_restricted():
    valve = make_valve()
    valve.anchors["X"].pressure = 9e6
    valve.anchors["Y"].pressure = 5e6  # P_X > P_Y -- restrito
    assert valve.get_visual_state() == "closed"


# ---------------------------------------------------------------------------
# Domínio pneumático (regressão -- não havia nenhum teste antes desta mudança)
# ---------------------------------------------------------------------------

def make_pneumatic_valve(delay_steps=3):
    valve = ThrottleCheckValve("tcv", domain="pneumatic", properties={"delay_steps": delay_steps})
    valve.add_anchor("X", domain="pneumatic")
    valve.add_anchor("Y", domain="pneumatic")
    return valve


def test_pneumatic_free_flow_connects_immediately():
    valve = make_pneumatic_valve()
    valve.anchors["X"].state = False
    valve.anchors["Y"].state = True
    valve.post_step_update(dt=0.1)
    assert valve.get_internal_connections() == [("X", "Y")]
    assert valve.get_visual_state() == "open"


def test_pneumatic_same_state_disconnects():
    valve = make_pneumatic_valve()
    valve.anchors["X"].state = True
    valve.anchors["Y"].state = True
    valve.post_step_update(dt=0.1)
    assert valve.get_internal_connections() == []


def test_pneumatic_restricted_direction_connects_only_after_delay():
    valve = make_pneumatic_valve(delay_steps=2)
    valve.anchors["X"].state = True
    valve.anchors["Y"].state = False

    valve.post_step_update(dt=0.1)
    assert valve.get_internal_connections() == []
    assert valve.get_visual_state() == "closed"

    valve.post_step_update(dt=0.1)
    assert valve.get_internal_connections() == [("X", "Y")]
