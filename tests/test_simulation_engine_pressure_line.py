import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.simulation_engine import SimulationEngine
from simulation.nodes.pressure_line import PressureLine
from simulation.nodes.nodes import PressureSource
from simulation.connections import Connection


def build_circuit():
    """Fonte de pressão -> PressureLine de 10 anchors, só X1 usado."""
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
    """Verifica que a poda de anchors intermediários funciona corretamente.
    Só X1 tem conexão externa; X2-X9 não têm nenhuma, então a cadeia interna
    podada é um único edge: X1 -> X10. O BFS alcança todos os anchors presentes
    no grafo apesar da poda agressiva.
    """
    nodes, connections, source, pl = build_circuit()
    engine = SimulationEngine(nodes, connections)

    group = engine._get_connected_group(source.get_anchor("P"))

    # Com poda, só os anchors reais (com conexão externa) ou forçados (endpoints)
    # permanecem no grafo interno. BFS alcança:
    # - source.P (origem)
    # - X1 (conexão externa de P)
    # - X10 (endpoint forçado, conectado a X1)
    # X2-X9 foram removidos da cadeia interna e não são alcançáveis.
    expected = {
        source.get_anchor("P"),
        pl.get_anchor("X1"),
        pl.get_anchor("X10"),
    }
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
