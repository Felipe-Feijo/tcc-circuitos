from simulation.nodes.nodes import Node

class PressureLine(Node):
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id=node_id, node_type="pressure_line", **kwargs)

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