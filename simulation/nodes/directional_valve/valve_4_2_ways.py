"""Nó de simulação de válvula direcional 4/2 vias."""


from simulation.nodes.directional_valve.directional_valve import DirectionalValve


class Valve_4_2_Ways(DirectionalValve):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "valve_4_2_ways", domain=domain, properties=properties)

    def get_internal_connections(self):
        """Retorna pares de anchors conectados internamente."""
        if self.body_state == 0:
            return [("P", "A"), ("B", "R")]
        else:
            return [("P", "B"), ("A", "R")]
        