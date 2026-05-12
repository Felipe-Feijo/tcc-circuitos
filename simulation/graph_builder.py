from simulation.connections import Connection

class GraphBuilder:
    def __init__(self):
        self.nodes = {}
        self.connections = {}
        self.node_map = {}
        self.connection_map = {}
        self._errors: list[str] = []   # acumula erros de props obrigatórias

    def add_node_from_item(self, node_item):
        node_cls = node_item.simulation_cls
        if node_cls is None:
            raise ValueError(
                f"{type(node_item).__name__} não define 'simulation_cls'. "
                "Declare o atributo de classe na subclasse de NodeItem."
            )

        try:
            node = node_cls(
                node_item.id,
                domain=node_item.domain,
                properties=getattr(node_item, "properties", {}),
            )
        except ValueError as e:
            self._errors.append(str(e))
            return None

        if hasattr(node_item, "anchor_list"):
            anchor_items = node_item.anchor_list
        else:
            anchor_items = node_item.anchors.values()

        for anchor_item in anchor_items:
            node.add_anchor(
                name=anchor_item.name,
                domain=anchor_item.domain
            )

        self.nodes[node.id] = node
        self.node_map[node_item] = node
        return node

    def raise_if_errors(self):
        """Lança ValueError consolidado se algum nó teve props faltando."""
        if self._errors:
            raise ValueError("\n".join(self._errors))

        # Determina a ordem das anchors
        if hasattr(node_item, "anchor_list"):
            # usa a lista ordenada
            anchor_items = node_item.anchor_list
        else:
            # fallback: dict.values(), ordem arbitrária
            anchor_items = node_item.anchors.values()

        for anchor_item in anchor_items:
            node.add_anchor(
                name=anchor_item.name,
                domain=anchor_item.domain
            )

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
