import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.simulation_engine import SimulationEngine
from simulation.nodes.pressure_line import PressureLine
from simulation.nodes.nodes import PressureSource
from simulation.connections import Connection


def build_circuit():
    """Fonte de pressão -> PressureLine de 10 anchors, só X1 e X5 usados."""
    source = PressureSource("src", domain="pneumatic")
    source.add_anchor("P", domain="pneumatic")

    pl = PressureLine("pl1", domain="pneumatic")
    for i in range(1, 11):
        pl.add_anchor(f"X{i}", domain="pneumatic")

    conn = Connection(source.get_anchor("P"), pl.get_anchor("X1"))

    nodes = {"src": source, "pl1": pl}
    connections = {conn.id: conn}
    return nodes, connections, source, pl


def test_connected_group_reaches_all_anchors_despite_pruned_edges():
    """Verifica que todos os anchors de uma PressureLine permanecem alcançáveis
    mesmo com o grafo interno podado. Se cada anchor tem uma conexão externa,
    a cadeia podada fica completa: X1-X2-X3-...-X10.
    """
    source = PressureSource("src", domain="pneumatic")
    source.add_anchor("P", domain="pneumatic")

    pl = PressureLine("pl1", domain="pneumatic")
    for i in range(1, 11):
        pl.add_anchor(f"X{i}", domain="pneumatic")

    # Cria conexões para CADA anchor para torná-los todos "reais"
    nodes = {"src": source, "pl1": pl}
    connections = {}

    # Conecta P a X1 como ponto de entrada
    conn_in = Connection(source.get_anchor("P"), pl.get_anchor("X1"))
    connections[conn_in.id] = conn_in

    # Cria "conexões fantasma" para os outros anchors
    # (conectando cada um a um nó dummy para torná-los "reais")
    exhaust_nodes = {}
    for i in range(2, 11):
        dummy_name = f"exhaust{i}"
        dummy = PressureSource(dummy_name, domain="pneumatic")
        dummy.add_anchor("R", domain="pneumatic")
        nodes[dummy_name] = dummy
        exhaust_nodes[i] = dummy

        anchor_name = f"X{i}"
        conn = Connection(pl.get_anchor(anchor_name), dummy.get_anchor("R"))
        connections[conn.id] = conn

    engine = SimulationEngine(nodes, connections)

    group = engine._get_connected_group(source.get_anchor("P"))

    # Com cada anchor tendo uma conexão, todos se tornam "reais"
    # A cadeia interna completa é: (X1,X2), (X2,X3), ..., (X9,X10)
    expected = {pl.get_anchor(f"X{i}") for i in range(1, 11)}
    expected.add(source.get_anchor("P"))
    for i in range(2, 11):
        expected.add(exhaust_nodes[i].get_anchor("R"))
    assert group == expected


def test_connected_group_stops_at_domain_boundary():
    nodes, connections, source, pl = build_circuit()
    engine = SimulationEngine(nodes, connections)

    # anchor hidráulico isolado não deve aparecer no grupo pneumático
    other = PressureLine("pl2", domain="hydraulic")
    other.add_anchor("Y1", domain="hydraulic")
    nodes["pl2"] = other

    group = engine._get_connected_group(source.get_anchor("P"))
    assert other.get_anchor("Y1") not in group
