"""Nó de simulação de fonte de tensão elétrica."""

from simulation.nodes.nodes import Node

class VoltageSource(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "voltage_source", domain=domain, properties=properties)

    def update(self, outputs=None):
        # marca todas as anchors como voltage_source + electric
        first_anchor = next(iter(self.anchors.values()))
        first_anchor.type = "source"

    def get_internal_connections(self):
        """
        Conecta todas as anchors em série:
        X1 -> X2 -> X3 -> ... -> Xn
        """
        names = list(self.anchors.keys())

        if len(names) < 2:
            return []
        
        return [
            (names[i], names[i + 1])
            for i in range(len(names) - 1)
        ]