import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

from simulation.nodes.check_valve.check_valve import CheckValve


def make_valve(piloted=False):
    valve = CheckValve("cv", domain="hydraulic", properties={"piloted": piloted})
    valve.add_anchor("X", domain="hydraulic")
    valve.add_anchor("Y", domain="hydraulic")
    valve.anchors["X"].pressure_var = "P_X"
    valve.anchors["Y"].pressure_var = "P_Y"
    if piloted:
        valve.add_anchor("Z", domain="hydraulic")
        valve.anchors["Z"].pressure_var = "P_Z"
    return valve


def make_idx(valve, piloted=False):
    idx = {valve.flow_var_x: 0, valve.flow_var_y: 1, "P_X": 2, "P_Y": 3}
    if piloted:
        idx[valve.flow_var_z] = 4
        idx["P_Z"] = 5
    return idx


# ---------------------------------------------------------------------------
# Conservação e ports/variables/bounds
# ---------------------------------------------------------------------------

def test_hydraulic_ports_include_z_only_when_piloted():
    valve = make_valve(piloted=False)
    assert set(valve.hydraulic_ports().keys()) == {"X", "Y"}

    piloted_valve = make_valve(piloted=True)
    assert set(piloted_valve.hydraulic_ports().keys()) == {"X", "Y", "Z"}


def test_variables_include_flow_and_pressure_vars():
    valve = make_valve(piloted=False)
    assert set(valve.variables) == {valve.flow_var_x, valve.flow_var_y, "P_X", "P_Y"}

    piloted_valve = make_valve(piloted=True)
    assert set(piloted_valve.variables) == {
        piloted_valve.flow_var_x, piloted_valve.flow_var_y, piloted_valve.flow_var_z,
        "P_X", "P_Y", "P_Z",
    }


def test_bounds_present_only_when_not_piloted():
    valve = make_valve(piloted=False)
    assert valve.bounds == {
        valve.flow_var_y: (0.0, None),
        valve.flow_var_x: (None, 0.0),
    }

    piloted_valve = make_valve(piloted=True)
    assert piloted_valve.bounds == {}


def test_pneumatic_domain_has_no_hydraulic_contract():
    valve = CheckValve("cv", domain="pneumatic", properties={})
    valve.add_anchor("X", domain="pneumatic")
    valve.add_anchor("Y", domain="pneumatic")
    assert valve.variables == []
    assert valve.hydraulic_ports() == {}
    assert valve.bounds == {}


# ---------------------------------------------------------------------------
# Complementaridade (Fischer-Burmeister) -- modo não pilotado
# ---------------------------------------------------------------------------

def test_conservation_equation_is_qx_plus_qy():
    valve = make_valve()
    idx = make_idx(valve)
    x = np.array([-1e-4, 1e-4, 3e6, 3e6])
    eq_conservation, _ = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9


def test_blocked_regime_is_exact_root_when_downstream_exceeds_upstream():
    """X (a jusante) mais pressurizado que Y (a montante) -- a esfera é
    empurrada contra o assento, bloqueada. Q=0 é raiz exata, mesmo com
    uma diferença de pressão enorme entre os dois lados."""
    valve = make_valve()
    idx = make_idx(valve)
    x = np.array([0.0, 0.0, 5e6, 0.0])  # P_X=5e6 >> P_Y=0, Q=0
    eq_conservation, eq_fb = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_fb) < 1e-9


def test_open_regime_is_exact_root_with_zero_pressure_drop():
    """Y consegue empurrar a esfera -- fluxo livre, sem queda de pressão."""
    valve = make_valve()
    idx = make_idx(valve)
    x = np.array([-1e-4, 1e-4, 3e6, 3e6])  # P_X == P_Y, Q_Y > 0
    eq_conservation, eq_fb = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_fb) < 1e-9


def test_inconsistent_point_is_not_a_root():
    """Sanity check: fluxo favorável (Q_Y>0) simultâneo com X muito mais
    pressurizado que Y não é uma solução válida -- o resíduo não deve
    ficar perto de zero."""
    valve = make_valve()
    idx = make_idx(valve)
    x = np.array([-1e-4, 1e-4, 5e6, 0.0])
    _, eq_fb = valve.equations(x, idx)
    assert abs(eq_fb) > 1e-3


# ---------------------------------------------------------------------------
# Pilotagem
# ---------------------------------------------------------------------------

def test_piloted_above_threshold_forces_zero_pressure_drop_ignoring_direction():
    """Piloto acima de 1 bar: a equação de complementaridade é substituída
    por uma simples igualdade de pressão -- mesmo com X mais pressurizado
    que Y (o que normalmente bloquearia), a válvula agora é uma passagem
    livre nos dois sentidos."""
    valve = make_valve(piloted=True)
    idx = make_idx(valve, piloted=True)
    # idx: 0=Q_X, 1=Q_Y, 2=P_X, 3=P_Y, 4=Q_Z, 5=P_Z
    x = np.array([1e-4, -1e-4, 5e6, 0.0, 0.0, 2e5])  # P_X >> P_Y, P_Z = 2 bar
    eqs = valve.equations(x, idx)
    assert len(eqs) == 3
    eq_conservation, eq_dp, eq_z = eqs
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_dp - (5e6 - 0.0) / valve.p_ref) < 1e-9
    assert abs(eq_z) < 1e-9


def test_piloted_below_threshold_still_uses_complementarity():
    valve = make_valve(piloted=True)
    idx = make_idx(valve, piloted=True)
    x = np.array([0.0, 0.0, 5e6, 0.0, 0.0, 5e4])  # P_X >> P_Y, P_Z = 0.5 bar (abaixo do limiar)
    eqs = valve.equations(x, idx)
    assert len(eqs) == 3
    eq_conservation, eq_fb, eq_z = eqs
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_fb) < 1e-9  # bloqueado, mesmo cálculo do modo não pilotado
    assert abs(eq_z) < 1e-9


def test_z_port_has_zero_flow_equation():
    valve = make_valve(piloted=True)
    idx = make_idx(valve, piloted=True)
    x = np.array([0.0, 0.0, 5e6, 0.0, 7.0, 5e4])  # Q_Z = 7 (não deveria ser raiz)
    _, _, eq_z = valve.equations(x, idx)
    assert abs(eq_z - 7.0 / valve.q_ref) < 1e-9
