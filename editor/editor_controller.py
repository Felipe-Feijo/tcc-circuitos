from simulation.graph_builder import GraphBuilder
from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.connections.connection_item import ConnectionItem
from simulation.debug import print_graph


class EditorController:
    def __init__(self, scene):
        self.scene = scene

    def build_graph(self):
        builder = GraphBuilder()

        # 1. Nodes
        for item in self.scene.items():
            if isinstance(item, NodeItem):
                builder.add_node_from_item(item)

        # 2. Conexões
        for item in self.scene.items():
            if isinstance(item, ConnectionItem):
                builder.add_connection_from_item(item)

        return builder

    def build_and_print_graph(self):
        builder = self.build_graph()
        print_graph(builder.nodes, builder.connections)