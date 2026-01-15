def debug_print_graph(self):
    from domain.graph_builder import GraphBuilder
    from domain.debug import print_graph

    builder = GraphBuilder(self.scene)
    components, connections = builder.build()

    print_graph(components, connections)

def print_graph(components, connections):
    """
    Debug helper that prints a human-readable representation
    of the domain graph built from the editor.
    """

    print("\n=== COMPONENTS ===")

    # Iterate over all domain components (dictionary values)
    for component in components.values():
        print(f"Component {component.id} ({component.type})")

        # Iterate over all anchors belonging to this component
        for anchor in component.anchors.values():

            # Collect all anchors connected to this anchor
            connected_anchors = []
            for connection in anchor.connections:
                other_anchor = (
                    connection.anchor_a
                    if connection.anchor_b == anchor
                    else connection.anchor_b
                )
                connected_anchors.append(other_anchor.id)

            print(f"  Anchor {anchor.name} -> {connected_anchors}")

    print("\n=== CONNECTIONS ===")

    # Print all connections explicitly
    for connection in connections:
        print(f"{connection.anchor_a.id} <--> {connection.anchor_b.id}")