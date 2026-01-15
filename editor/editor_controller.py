from domain.graph_builder import GraphBuilder
from graphics.items.nodes.component_item import ComponentItem
from graphics.items.connections.connection_item import ConnectionItem
from domain.debug import print_graph


class EditorController:
    def __init__(self, scene):
        self.scene = scene

    def build_graph(self):
        builder = GraphBuilder()

        # 1. Componentes
        for item in self.scene.items():
            if isinstance(item, ComponentItem):
                builder.add_component_from_item(item)

        # 2. Conexões
        for item in self.scene.items():
            if isinstance(item, ConnectionItem):
                builder.add_connection_from_item(item)

        return builder

    def build_and_print_graph(self):
        builder = self.build_graph()
        print_graph(builder.components, builder.connections)