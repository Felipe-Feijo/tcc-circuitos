"""Reprodução do crash: conexão para um nó com propriedade obrigatória
ausente não deve derrubar build_graph() com KeyError -- o erro já foi
acumulado por add_node_from_item() e deve ser reportado por
raise_if_errors(), não por uma exceção não tratada no meio da varredura."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.relief_valve import ReliefValve
from graphics.items.base.nodes.check_valve.check_valve import CheckValve
from graphics.items.base.connections.connection_item import ConnectionItem
from simulation.graph_builder import GraphBuilder


def test_connection_to_node_with_missing_required_property_does_not_crash():
    # ReliefValve sem 'p_set' setado -- falha ao criar o nó de domínio.
    relief = ReliefValve(domain="hydraulic")
    valve = CheckValve(domain="hydraulic")
    conn = ConnectionItem(relief, relief.anchors["T"], valve, valve.anchors["X"])

    builder = GraphBuilder()
    builder.add_node_from_item(relief)
    builder.add_node_from_item(valve)

    # Não deve levantar KeyError -- o nó do relief falhou e não está em
    # builder.nodes, então a conexão que o referencia deve ser ignorada
    # (o erro já foi acumulado e será reportado por raise_if_errors()).
    builder.add_connection_from_item(conn)

    with pytest.raises(ValueError, match="p_set"):
        builder.raise_if_errors()
