"""Syncs domain state back to the graphics items after each step."""


class ViewSync:
    """Pushes domain state to the graphics items after each step.

    Decoupled from QObject -- uses no signals, just direct method calls.

    Attributes:
        node_map: Mapping of NodeItem to its corresponding domain node.
        connection_map: Mapping of ConnectionItem to its domain connection.
    """

    def __init__(self):
        self.node_map: dict = {}
        self.connection_map: dict = {}

    def sync(self) -> None:
        """Visually updates all graphics items with the current domain state.

        Calls update_from_domain on each NodeItem and set_state on each ConnectionItem.
        """
        for node_item, domain_node in self.node_map.items():
            node_item.update_from_domain(domain_node)

        for conn_item, domain_conn in self.connection_map.items():
            conn_item.set_state(domain_conn.get_state())
