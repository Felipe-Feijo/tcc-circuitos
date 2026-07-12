"""Nó de simulação de linha de pressão pneumática."""

from simulation.nodes.nodes import Node
from simulation.nodes.anchor_chain import real_anchor_chain


class PressureLine(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "pressure_line", domain=domain, properties=properties)

    def get_internal_connections(self):
        """
        Conecta apenas os anchors reais (com conexão externa) em série,
        sempre incluindo as duas pontas da linha:
        X1 -> X3 -> X40 -> ... -> Xn
        """
        names = list(self.anchors.keys())

        if len(names) < 2:
            return []

        def is_real(name):
            return len(self.anchors[name].connections) > 0

        return real_anchor_chain(names, is_real)