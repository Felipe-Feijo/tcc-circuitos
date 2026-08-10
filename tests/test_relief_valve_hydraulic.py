import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

from simulation.nodes.relief_valve import ReliefValve


def make_valve(piloted=False, p_set=1.5e7):
    props = {"p_set": p_set}
    if piloted:
        props["piloted"] = True
    valve = ReliefValve("rv", domain="hydraulic", properties=props)
    valve.add_anchor("P", domain="hydraulic")
    valve.add_anchor("T", domain="hydraulic")
    valve.anchors["P"].pressure_var = "P_P"
    valve.anchors["T"].pressure_var = "P_T"
    if piloted:
        valve.add_anchor("Y", domain="hydraulic")
        valve.anchors["Y"].pressure_var = "P_Y"
        # sentinela -- simula Y conectada a algo, já que este helper não
        # monta um grafo de conexões real. Testes que exercitam o caso
        # "Y desconectada" removem isto explicitamente.
        valve.anchors["Y"].connections.append(object())
    return valve


def make_idx(valve, piloted=False):
    idx = {valve.flow_var_in: 0, valve.flow_var_out: 1, "P_P": 2, "P_T": 3}
    if piloted:
        idx[valve.flow_var_y] = 4
        idx["P_Y"] = 5
    return idx


# ---------------------------------------------------------------------------
# node_type / ports / variables / bounds
# ---------------------------------------------------------------------------

def test_node_type_is_relief_valve():
    valve = make_valve()
    assert valve.type == "relief_valve"


def test_hydraulic_ports_include_y_only_when_piloted():
    valve = make_valve(piloted=False)
    assert set(valve.hydraulic_ports().keys()) == {"P", "T"}

    piloted_valve = make_valve(piloted=True)
    assert set(piloted_valve.hydraulic_ports().keys()) == {"P", "T", "Y"}


def test_variables_include_y_flow_and_pressure_when_piloted():
    valve = make_valve(piloted=False)
    assert set(valve.variables) == {valve.flow_var_in, valve.flow_var_out, "P_P", "P_T"}

    piloted_valve = make_valve(piloted=True)
    assert set(piloted_valve.variables) == {
        piloted_valve.flow_var_in, piloted_valve.flow_var_out, piloted_valve.flow_var_y,
        "P_P", "P_T", "P_Y",
    }


def test_bounds_unaffected_by_piloted():
    valve = make_valve(piloted=False)
    assert valve.bounds == {
        valve.flow_var_in: (0.0, None),
        valve.flow_var_out: (None, 0.0),
    }

    piloted_valve = make_valve(piloted=True)
    assert piloted_valve.bounds == {
        piloted_valve.flow_var_in: (0.0, None),
        piloted_valve.flow_var_out: (None, 0.0),
    }


# ---------------------------------------------------------------------------
# Regressão -- comportamento não pilotado idêntico ao de antes do rename
# ---------------------------------------------------------------------------

def test_non_piloted_closed_regime_is_exact_root_below_p_set():
    valve = make_valve(piloted=False, p_set=1.5e7)
    idx = make_idx(valve)
    x = np.array([0.0, 0.0, 1.0e7, 0.0])  # P_in bem abaixo de p_set, Q=0
    eq_conservation, eq_fb = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_fb) < 1e-9


def test_non_piloted_open_regime_is_exact_root_above_p_set():
    valve = make_valve(piloted=False, p_set=1.5e7)
    idx = make_idx(valve)
    x = np.array([1e-4, -1e-4, 2e7, 2e7])  # P_in == P_out == 2e7 > p_set
    eq_conservation, eq_fb = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_fb) < 1e-9


# ---------------------------------------------------------------------------
# Pilotagem -- limiar efetivo = p_set + P_y
# ---------------------------------------------------------------------------

def test_closed_regime_residual_uses_effective_threshold_with_pilot():
    """No mesmo P_in, acima de p_set sozinho mas abaixo de p_set + P_y:
    sem pilotagem o regime fechado (Q=0) NÃO é raiz (a válvula "quer"
    abrir); com pilotagem suficiente, volta a ser raiz (permanece
    fechada)."""
    p_set = 1.5e7
    p_in = 1.55e7  # acima de p_set sozinho

    valve = make_valve(piloted=False, p_set=p_set)
    idx = make_idx(valve)
    x = np.array([0.0, 0.0, p_in, 0.0])
    _, eq_fb = valve.equations(x, idx)
    assert abs(eq_fb) > 1e-6  # não é raiz -- P_in já passou de p_set sozinho

    piloted_valve = make_valve(piloted=True, p_set=p_set)
    idx2 = make_idx(piloted_valve, piloted=True)
    p_y = 1e6  # 10 bar -- eleva o limiar efetivo pra 1.6e7, acima de P_in
    x2 = np.array([0.0, 0.0, p_in, 0.0, 0.0, p_y])
    eq_conservation, eq_fb2, eq_y = piloted_valve.equations(x2, idx2)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_fb2) < 1e-9  # com o piloto, o limiar sobe e a raiz fechada volta a valer
    assert abs(eq_y) < 1e-9


def test_piloted_open_regime_also_uses_effective_threshold():
    """No regime aberto, o gate `P_out > effective_p_set` também precisa
    considerar P_y -- senão a válvula abriria cedo demais mesmo com
    pilotagem alta."""
    p_set = 1.5e7
    p_y = 1e6  # eleva o limiar efetivo pra 1.6e7

    valve = make_valve(piloted=True, p_set=p_set)
    idx = make_idx(valve, piloted=True)
    # P_out = 1.55e7 (> p_set sozinho, mas < p_set + p_y) -- não deveria
    # satisfazer o gate de regime aberto.
    x = np.array([0.0, 0.0, 1.55e7, 1.55e7, 0.0, p_y])
    _, eq_fb, _ = valve.equations(x, idx)
    # No regime fechado com Q_in=0: a = (effective_p_set - P_in)/P_scale > 0, b=0 -> raiz.
    assert abs(eq_fb) < 1e-9


def test_effective_p_set_is_exactly_p_set_plus_p_y_not_a_larger_multiple():
    """Ancora a fórmula pelos dois lados: um P_in acima de p_set + p_y é
    raiz no regime aberto; um P_in estritamente entre p_set + p_y e
    p_set + 2*p_y NÃO é raiz em nenhum regime -- isso só é verdade se o
    limiar efetivo for exatamente p_set + p_y (uma fórmula errada como
    p_set + 2*p_y tornaria esse segundo P_in uma raiz do regime fechado)."""
    p_set = 1.5e7
    p_y = 1e6
    threshold = p_set + p_y  # 1.6e7

    # ---- lado 1: regime aberto, P_in e P_out acima do limiar, Q_in > 0 ----
    valve = make_valve(piloted=True, p_set=p_set)
    idx = make_idx(valve, piloted=True)
    p_above = threshold + 1e6  # 1.7e7 -- bem acima do limiar efetivo
    x_open = np.array([1e-4, -1e-4, p_above, p_above, 0.0, p_y])
    _, eq_fb_open, _ = valve.equations(x_open, idx)
    assert abs(eq_fb_open) < 1e-9  # eq_fb = (P_in - P_out)/P_scale = 0 -- raiz

    # ---- lado 2: P_in estritamente entre threshold e p_set + 2*p_y ----
    valve2 = make_valve(piloted=True, p_set=p_set)
    idx2 = make_idx(valve2, piloted=True)
    p_between = p_set + 1.5 * p_y  # 1.65e7 -- entre threshold (1.6e7) e p_set+2*p_y (1.7e7)
    x_closed = np.array([0.0, 0.0, p_between, 0.0, 0.0, p_y])
    _, eq_fb_closed, _ = valve2.equations(x_closed, idx2)
    # Só não é raiz se o limiar efetivo for 1.6e7 (P_in já passou dele);
    # se a fórmula usasse p_set + 2*p_y (1.7e7), P_in ainda estaria abaixo
    # do limiar e isso seria (erroneamente) uma raiz.
    assert abs(eq_fb_closed) > 1e-6


def test_piloted_with_unconnected_y_raises_value_error():
    """Y pilotada mas nunca conectada a nada -- P_y ficaria com o seed
    default (p_ref, igual a p_set), dobrando silenciosamente o limiar
    efetivo. Deve falhar alto e claro em vez de simular errado."""
    valve = make_valve(piloted=True)
    idx = make_idx(valve, piloted=True)
    valve.anchors["Y"].connections.clear()  # desfaz o sentinela do helper
    assert valve.anchors["Y"].connections == []
    x = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    try:
        valve.equations(x, idx)
        assert False, "esperava ValueError para Y pilotada desconectada"
    except ValueError as e:
        assert "Y" in str(e)


def test_piloted_with_connected_y_does_not_raise():
    """Com pelo menos uma conexão em Y.connections (já fornecida pelo
    helper make_valve), a validação passa e equations() não levanta."""
    valve = make_valve(piloted=True)
    idx = make_idx(valve, piloted=True)
    assert valve.anchors["Y"].connections  # helper já conectou o sentinela
    x = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    valve.equations(x, idx)  # não deve levantar


# ---------------------------------------------------------------------------
# Regressão -- criação de âncoras via mapa estático (tests/simulate_json.py)
# ---------------------------------------------------------------------------

def test_piloted_valve_built_like_simulate_json_does_not_raise_keyerror():
    """tests/simulate_json.py cria âncoras a partir de um mapa estático
    ANCHORS_BY_TYPE antes de aplicar properties. Para um ReliefValve com
    piloted=True, isso precisa incluir 'Y', senão equations() explode com
    KeyError ao tentar ler self.anchors['Y']. Este teste replica o padrão
    de load_circuit() em tests/simulate_json.py."""
    from tests.simulate_json import ANCHORS_BY_TYPE

    props = {"p_set": 1.5e7, "piloted": True}
    valve = ReliefValve("rv2", domain="hydraulic", properties=props)

    anchor_names = ANCHORS_BY_TYPE.get("ReliefValve", [])
    if props.get("piloted"):
        anchor_names = anchor_names + ["Y"]
    for aname in anchor_names:
        valve.add_anchor(aname, "hydraulic")

    assert set(valve.hydraulic_ports().keys()) <= set(valve.anchors.keys())

    for aname, anchor in valve.anchors.items():
        anchor.pressure_var = f"P_{aname}"
    valve.anchors["Y"].connections.append(object())

    idx = {
        valve.flow_var_in: 0, valve.flow_var_out: 1,
        valve.flow_var_y: 2,
        "P_P": 3, "P_T": 4, "P_Y": 5,
    }
    x = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    valve.equations(x, idx)  # não deve levantar KeyError


def test_y_port_has_zero_flow_equation():
    valve = make_valve(piloted=True)
    idx = make_idx(valve, piloted=True)
    x = np.array([0.0, 0.0, 0.0, 0.0, 7.0, 0.0])  # Q_Y = 7 (não deveria ser raiz)
    eqs = valve.equations(x, idx)
    eq_y = eqs[-1]
    assert abs(eq_y - 7.0 / valve.q_ref) < 1e-9
