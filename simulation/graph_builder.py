# domain/graph_builder.py

from simulation.nodes.nodes import Valve3_2, PressureSource, Exhaust, Piston
from simulation.connections import Connection

NODE_FACTORY = {
    "valve_3_2_ways": Valve3_2,
    "pressure_source": PressureSource,
    "exhaust": Exhaust,
    "piston": Piston,
}

class GraphBuilder:
    def __init__(self):
        self.nodes = {}
        self.connections = {}
        self.node_map = {}        # NodeItem -> DomainNode
        self.connection_map = {}  # ConnectionItem -> DomainConnection

    def add_node_from_item(self, node_item):
        node_cls = NODE_FACTORY[node_item.node_type]
        node = node_cls(node_item.id)

        self.nodes[node.id] = node
        self.node_map[node_item] = node
        return node
    
    def add_connection_from_item(self, connection_item):
        """
        Create a domain Connection from a graphical ConnectionItem.
        """

        # Graphical anchor items at both ends of the connection
        source_anchor_item = connection_item.source_anchor
        target_anchor_item = connection_item.target_anchor

        # Domain nodes owning those anchors
        source_node = self.nodes[source_anchor_item.node.id]
        target_node = self.nodes[target_anchor_item.node.id]

        # Domain anchors corresponding to the graphical anchors
        source_anchor = source_node.get_anchor(source_anchor_item.name)
        target_anchor = target_node.get_anchor(target_anchor_item.name)

        # Create the domain connection (non-directional)
        connection = Connection(source_anchor, target_anchor)

        if connection.id not in self.connections:
            self.connections[connection.id] = connection
            self.connection_map[connection_item] = connection

        return self.connections[connection.id]
