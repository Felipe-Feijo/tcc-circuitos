"""Simulation node for the electrical voltage source."""

from simulation.nodes.nodes import Node


class VoltageSource(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "voltage_source", domain=domain, properties=properties)

    def update(self, outputs=None):
        self.get_anchor("X1").type = "source"
