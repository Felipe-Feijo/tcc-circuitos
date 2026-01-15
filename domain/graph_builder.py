# domain/graph_builder.py

from domain.components import Component
from domain.connections import Connection


class GraphBuilder:
    def __init__(self):
        self.components = {}
        self.connections = []

    def add_component_from_item(self, component_item):
        """
        Create a domain Component from a graphical ComponentItem.
        """

        # Create the domain-level component
        component = Component(
            component_id=component_item.id,
            comp_type=component_item.component_type,
        )

        # Create domain anchors based on the graphical anchors
        for anchor_item in component_item.anchors:
            component.add_anchor(anchor_item.name)

        self.components[component.id] = component
        return component

    def add_connection_from_item(self, connection_item):
        """
        Create a domain Connection from a graphical ConnectionItem.
        """

        # Graphical anchor items at both ends of the connection
        source_anchor_item = connection_item.source_anchor
        target_anchor_item = connection_item.target_anchor

        # Domain components owning those anchors
        source_component = self.components[source_anchor_item.component.id]
        target_component = self.components[target_anchor_item.component.id]

        # Domain anchors corresponding to the graphical anchors
        source_anchor = source_component.get_anchor(source_anchor_item.name)
        target_anchor = target_component.get_anchor(target_anchor_item.name)

        # Create the domain connection (non-directional)
        connection = Connection(source_anchor, target_anchor)
        self.connections.append(connection)

        return connection
