"""Editor controller: builds the simulation graph from the graphics scene."""

from simulation.graph_builder import GraphBuilder
from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.connections.connection_item import ConnectionItem


class EditorController:
    """Coordinates editor operations on the simulation graph.

    Responsible for scanning the graphics scene and building the domain
    representation (nodes and connections) used by SimulationEngine.
    """

    def __init__(self, scene):
        self.scene = scene

    def build_graph(self) -> GraphBuilder:
        """Scans the scene and builds the simulation graph.

        Walks all scene items in two passes: first registers the nodes,
        then the connections (which depend on the nodes already being
        in the graph).

        Returns:
            GraphBuilder populated with the current scene's nodes and connections.
        """
        builder = GraphBuilder()

        for item in self.scene.items():
            if isinstance(item, NodeItem):
                builder.add_node_from_item(item)

        for item in self.scene.items():
            if isinstance(item, ConnectionItem):
                builder.add_connection_from_item(item)

        return builder
