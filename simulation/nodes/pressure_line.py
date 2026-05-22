"""Nó de simulação de linha de pressão pneumática."""

from simulation.nodes.nodes import Node

class PressureLine(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "pressure_line", domain=domain, properties=properties)

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