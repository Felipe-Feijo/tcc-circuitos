class ViewSync:
    """Pushes domain state into graphical items after each simulation step.

    Decoupled from QObject — no signals needed, just plain method calls.
    """

    def __init__(self):
        self.node_map: dict = {}        # NodeItem  -> DomainNode
        self.connection_map: dict = {}  # ConnectionItem -> DomainConnection

    def sync(self) -> None:
        """Call update_from_domain on each NodeItem and set_state on each ConnectionItem."""
        for node_item, domain_node in self.node_map.items():
            node_item.update_from_domain(domain_node)

        for conn_item, domain_conn in self.connection_map.items():
            conn_item.set_state(domain_conn.get_state())