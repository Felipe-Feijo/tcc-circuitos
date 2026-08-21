"""Simulation node for the electrical ground reference."""

from simulation.nodes.nodes import Node


class Ground(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "ground", domain=domain, properties=properties)

    def update(self, outputs=None):
        self.get_anchor("X1").type = "ground"
