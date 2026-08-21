"""Simulation node for the pneumatic pressure line."""

from simulation.nodes.nodes import Node
from simulation.nodes.anchor_chain import real_anchor_chain


class PressureLine(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "pressure_line", domain=domain, properties=properties)

    def get_internal_connections(self):
        """
        Connects only the real anchors (with an external connection) in
        series, always including both ends of the line:
        X1 -> X3 -> X40 -> ... -> Xn
        """
        names = list(self.anchors.keys())

        if len(names) < 2:
            return []

        def is_real(name):
            return len(self.anchors[name].connections) > 0

        return real_anchor_chain(names, is_real)