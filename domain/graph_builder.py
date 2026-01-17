# domain/graph_builder.py

from domain.nodes import Node
from domain.connections import Connection


class GraphBuilder:
    def __init__(self):
        self.nodes = {}
        self.connections = []

    def add_node_from_item(self, node_item):
        """
        Create a domain Node from a graphical NodeItem.
        """

        # Create the domain-level node
        node = Node(
            node_id=node_item.id,
            node_type=node_item.node_type,
        )

        # Create domain anchors based on the graphical anchors
        for anchor_item in node_item.anchors:
            node.add_anchor(anchor_item.name)

        self.nodes[node.id] = node
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
        self.connections.append(connection)

        return connection
