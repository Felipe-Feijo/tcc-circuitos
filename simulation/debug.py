from simulation.nodes.nodes import Piston
from simulation.simulation_engine import SimulationEngine


def debug_print_graph(self):
    from simulation.graph_builder import GraphBuilder
    from simulation.debug import print_graph

    builder = GraphBuilder(self.scene)
    nodes, connections = builder.build()

    print_graph(nodes, connections)

def print_graph(nodes, connections):
    """
    Debug helper that prints a human-readable representation
    of the domain graph built from the editor.
    """

    print("\n=== NODES ===")

    # Iterate over all domain nodes (dictionary values)
    for node in nodes.values():
        print(f"Node {node.id} ({node.type})")
        # Iterate over all anchors belonging to this node
        for anchor in node.anchors.values():

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

