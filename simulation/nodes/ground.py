from simulation.nodes.nodes import Node

class Ground(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "ground", domain=domain, properties=properties)

    def update(self, outputs=None):
        # marca apenas a primeira anchor como ground
        first_anchor = next(iter(self.anchors.values()))
        first_anchor.type = "ground"

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