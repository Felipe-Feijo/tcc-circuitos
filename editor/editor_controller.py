"""Controlador do editor: constrói o grafo de simulação a partir da cena gráfica."""

from simulation.graph_builder import GraphBuilder
from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.connections.connection_item import ConnectionItem


class EditorController:
    """Coordena operações do editor sobre o grafo de simulação.

    Responsável por varrer a cena gráfica e construir a representação
    de domínio (nós e conexões) usada pelo SimulationEngine.
    """

    def __init__(self, scene):
        self.scene = scene

    def build_graph(self) -> GraphBuilder:
        """Varre a cena e constrói o grafo de simulação.

        Percorre todos os itens da cena em duas passagens: primeiro
        registra os nós, depois as conexões (que dependem dos nós
        já estarem no grafo).

        Returns:
            GraphBuilder populado com os nós e conexões da cena atual.
        """
        builder = GraphBuilder()

        for item in self.scene.items():
            if isinstance(item, NodeItem):
                builder.add_node_from_item(item)

        for item in self.scene.items():
            if isinstance(item, ConnectionItem):
                builder.add_connection_from_item(item)

        return builder
