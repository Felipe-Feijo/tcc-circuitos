import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.nodes.check_valve.check_valve import CheckValve


def make_node(piloted=False, with_z_anchor=None):
    """with_z_anchor: força a criação da anchor Z mesmo com piloted=False,
    pra testar que a propriedade (não a mera presença da anchor) controla
    a lógica de força."""
    node = CheckValve("n1", domain="pneumatic", properties={"piloted": piloted})
    node.add_anchor("X", domain="pneumatic")
    node.add_anchor("Y", domain="pneumatic")
    if piloted or with_z_anchor:
        node.add_anchor("Z", domain="pneumatic")
    return node


def test_x_is_driver_while_conducting():
    node = make_node()
    node.anchors["Y"].state = True
    node.update()
    assert node.anchors["X"].is_driver is True


def test_x_is_not_driver_when_not_conducting():
    """Essencial: se X ficasse driver pra sempre, o algoritmo de grupo do
    motor nunca mais atualizaria o PRÓPRIO X (drivers não são
    sobrescritos), então X reportaria um True obsoleto mesmo depois de uma
    exaustão real desafogar o resto do circuito a jusante."""
    node = make_node()
    node.anchors["Y"].state = False
    node.update()
    assert node.anchors["X"].is_driver is False


def test_free_flow_latches_x_to_true():
    node = make_node()
    node.anchors["Y"].state = True
    node.update()
    assert node.anchors["X"].state is True
    assert node.get_visual_state() == "open"


def test_y_false_does_not_touch_x():
    node = make_node()
    node.anchors["X"].state = False
    node.anchors["Y"].state = False
    node.update()
    assert node.anchors["X"].state is False
    assert node.get_visual_state() == "closed"


def test_x_stays_latched_true_after_y_drops_back_to_false():
    """O caso central de um check valve de verdade: uma vez que a pressão
    passou (Y=1 -> X vira 1), se Y depois cair pra 0 (a fonte a montante
    sumiu ou foi trocada por exaustão), X deve continuar 1 -- a pressão
    fica retida a jusante até algo além desta válvula desafogar."""
    node = make_node()
    node.anchors["Y"].state = True
    node.update()
    assert node.anchors["X"].state is True

    node.anchors["Y"].state = False
    node.update()
    assert node.anchors["X"].state is True
    assert node.anchors["X"].is_driver is False  # virou seguidor comum de novo
    assert node.get_visual_state() == "closed"  # válvula fecha, mas pressão fica retida


def test_pilot_forces_x_true_even_when_y_false():
    node = make_node(piloted=True)
    node.anchors["Y"].state = False
    node.anchors["Z"].state = True
    node.update()
    assert node.anchors["X"].state is True
    assert node.get_visual_state() == "open"


def test_piloted_false_ignores_z_state_even_if_anchor_present():
    node = make_node(piloted=False, with_z_anchor=True)
    node.anchors["Y"].state = False
    node.anchors["Z"].state = True
    node.update()
    assert node.anchors["X"].state is False
    assert node.get_visual_state() == "closed"


def test_get_internal_connections_is_always_empty():
    """X e Y nunca são unidos num grupo simétrico -- ver docstring do
    módulo simulation/nodes/check_valve/check_valve.py para o porquê
    (união simétrica não representa um diodo: um exaustão alcançável
    later por Y arrastaria X pra baixo também)."""
    node = make_node()
    node.anchors["Y"].state = True
    node.update()
    assert node.get_internal_connections() == []


def test_get_state_and_set_state_roundtrip():
    node = make_node()
    node.anchors["Y"].state = True
    node.update()
    state = node.get_state()

    node2 = make_node()
    node2.set_state(state)
    assert node2.anchors["X"].state is True
    assert node2.get_visual_state() == "open"


def test_trapped_pressure_survives_upstream_source_removal_end_to_end():
    """Regressão de ponta a ponta reproduzindo o bug relatado: um cilindro
    (representado aqui por um Node genérico a jusante de X) que avançou
    através da retenção não deve recuar quando a válvula direcional a
    montante comuta de fornecimento pra exaustão em Y."""
    from simulation.simulation_engine import SimulationEngine
    from simulation.nodes.nodes import Node, PressureSource, Exhaust
    from simulation.connections import Connection

    source = PressureSource("src", domain="pneumatic")
    source.add_anchor("P", domain="pneumatic")

    exhaust = Exhaust("exh", domain="pneumatic")
    exhaust.add_anchor("R", domain="pneumatic")

    valve = CheckValve("cv", domain="pneumatic", properties={})
    valve.add_anchor("X", domain="pneumatic")
    valve.add_anchor("Y", domain="pneumatic")

    downstream = Node("dn", "generic", domain="pneumatic")
    downstream.add_anchor("D", domain="pneumatic")

    conn_y = Connection(valve.get_anchor("Y"), source.get_anchor("P"))
    conn_x = Connection(valve.get_anchor("X"), downstream.get_anchor("D"))

    nodes = {"src": source, "cv": valve, "dn": downstream}
    connections = {conn_y.id: conn_y, conn_x.id: conn_x}

    engine = SimulationEngine(nodes, connections)
    engine.run_until_stable()

    assert downstream.get_anchor("D").state is True

    # Simula a válvula direcional a montante comutando: Y deixa de ver a
    # fonte e passa a ver uma exaustão.
    valve.get_anchor("Y").connections.remove(conn_y)
    source.get_anchor("P").connections.remove(conn_y)
    conn_y2 = Connection(valve.get_anchor("Y"), exhaust.get_anchor("R"))

    nodes["exh"] = exhaust
    del connections[conn_y.id]
    connections[conn_y2.id] = conn_y2

    engine.run_until_stable()

    assert downstream.get_anchor("D").state is True  # continua retido, não vaza


def test_trapped_pressure_can_still_be_vented_by_a_real_downstream_exhaust():
    """Prova que X não vira um driver 'zumbi' permanente: depois de reter
    pressão, se uma exaustão REAL for conectada no grupo a jusante de X
    (ex: o usuário liga um exaustão na mangueira do lado de X), o valor
    deve ser corretamente desafogado -- não fica preso pra sempre só
    porque em algum momento X foi driver."""
    from simulation.simulation_engine import SimulationEngine
    from simulation.nodes.nodes import Node, Exhaust
    from simulation.connections import Connection

    valve = CheckValve("cv", domain="pneumatic", properties={})
    valve.add_anchor("X", domain="pneumatic")
    valve.add_anchor("Y", domain="pneumatic")

    downstream = Node("dn", "generic", domain="pneumatic")
    downstream.add_anchor("D", domain="pneumatic")

    conn_x = Connection(valve.get_anchor("X"), downstream.get_anchor("D"))
    nodes = {"cv": valve, "dn": downstream}
    connections = {conn_x.id: conn_x}

    engine = SimulationEngine(nodes, connections)

    # Conduz uma vez para reter pressão em X/downstream.
    valve.get_anchor("Y").state = True
    engine.run_until_stable()
    assert downstream.get_anchor("D").state is True

    # Y volta a 0 (válvula fecha) -- pressão deve continuar retida.
    valve.get_anchor("Y").state = False
    engine.run_until_stable()
    assert downstream.get_anchor("D").state is True

    # Uma exaustão real é conectada no lado de X (não pela retenção).
    exhaust = Exhaust("exh", domain="pneumatic")
    exhaust.add_anchor("R", domain="pneumatic")
    conn_exh = Connection(downstream.get_anchor("D"), exhaust.get_anchor("R"))
    nodes["exh"] = exhaust
    connections[conn_exh.id] = conn_exh

    engine.run_until_stable()

    assert downstream.get_anchor("D").state is False
    assert valve.get_anchor("X").state is False  # X também é corrigido, não fica obsoleto
