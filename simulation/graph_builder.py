"""Builds the simulation graph from the scene's graphics items."""

from simulation.connections import Connection


class GraphBuilder:
    """Converts the scene's graphics items into simulation-domain nodes and connections.

    Typical usage by EditorController:
        builder = GraphBuilder()
        builder.add_node_from_item(node_item)       # for each NodeItem
        builder.add_connection_from_item(conn_item) # for each ConnectionItem
        builder.raise_if_errors()
    """

    def __init__(self):
        self.nodes: dict = {}
        self.connections: dict = {}
        self.node_map: dict = {}
        self.connection_map: dict = {}
        self._errors: list[str] = []

    def add_node_from_item(self, node_item):
        """Creates the domain node corresponding to a graphics NodeItem.

        Args:
            node_item: A NodeItem instance present in the scene.

        Returns:
            The created domain node, or None if creation failed due to
            missing required properties (the error is accumulated
            internally and can be raised via raise_if_errors).

        Raises:
            ValueError: If the NodeItem subclass doesn't declare simulation_cls.
        """
        node_cls = node_item.simulation_cls
        if node_cls is None:
            raise ValueError(
                f"{type(node_item).__name__} doesn't define 'simulation_cls'. "
                "Declare the class attribute in the NodeItem subclass."
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

        for anchor_item in node_item.anchors.values():
            node.add_anchor(name=anchor_item.name, domain=anchor_item.domain)

        self.nodes[node.id] = node
        self.node_map[node_item] = node
        return node

    def add_connection_from_item(self, connection_item):
        """Creates the domain connection corresponding to a graphics ConnectionItem.

        Args:
            connection_item: A ConnectionItem instance present in the scene.

        Returns:
            The created domain Connection, or None if one of the nodes
            wired to this connection failed to be created (a required
            property is missing -- the error was already accumulated by
            add_node_from_item and will be reported by
            raise_if_errors(); there's no node to connect to).
        """
        source_anchor_item = connection_item.source_anchor
        target_anchor_item = connection_item.target_anchor

        source_node = self.nodes.get(source_anchor_item.node.id)
        target_node = self.nodes.get(target_anchor_item.node.id)
        if source_node is None or target_node is None:
            return None

        source_anchor = source_node.get_anchor(source_anchor_item.name)
        target_anchor = target_node.get_anchor(target_anchor_item.name)

        connection = Connection(source_anchor, target_anchor)

        if connection.id not in self.connections:
            self.connections[connection.id] = connection
            self.connection_map[connection_item] = connection

        return self.connections[connection.id]

    def raise_if_errors(self) -> None:
        """Raises a consolidated ValueError if any node has missing required
        properties or an unconnected dead (sensing-only) port.

        Raises:
            ValueError: Combined message of every accumulated error.
        """
        self._validate_dead_ports()
        if self._errors:
            raise ValueError("\n".join(self._errors))

    def _validate_dead_ports(self) -> None:
        """Pre-flight check for sensing-only ports (e.g. a valve's pilot
        line 'Y') that carry no flow but still must be wired to something.
        Left unconnected, such a port silently seeds a default pressure
        instead of failing -- checking here, before the engine exists,
        turns that into one clear message instead of an exception raised
        mid-solve. Optional hook: nodes without dead ports don't define
        `dead_ports()` at all."""
        for node in self.nodes.values():
            dead_ports = getattr(node, "dead_ports", None)
            if dead_ports is None:
                continue
            for port_name in dead_ports():
                anchor = node.anchors.get(port_name)
                if anchor is None or not anchor.connections:
                    self._errors.append(
                        f"{type(node).__name__} '{node.id}': port '{port_name}' is not connected to anything."
                    )
