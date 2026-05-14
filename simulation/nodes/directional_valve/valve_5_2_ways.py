from simulation.nodes.directional_valve.directional_valve import DirectionalValve


class Valve_5_2_Ways(DirectionalValve):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "valve_5_2_ways", domain=domain, properties=properties)

    def get_internal_connections(self):
        """Retorna pares de anchors conectados internamente.
        
        Estado 0 (repouso): P→B, A→R1
        Estado 1 (ativo):   P→A, B→R2
        """
        if self.body_state == 0:
            return [("P", "B"), ("A", "R1")]
        else:
            return [("P", "A"), ("B", "R2")]