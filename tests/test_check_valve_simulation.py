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


def test_x_becomes_a_driver_after_update():
    node = make_node()
    node.update()
    assert node.anchors["X"].is_driver is True


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
