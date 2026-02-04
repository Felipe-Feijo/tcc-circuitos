from simulation.nodes.directional_valve.directional_valve import DirectionalValve


class Valve_3_2_Ways(DirectionalValve):
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id, "valve_3_2_ways", **kwargs)

        # Anchors
        self.add_anchor("P")
        self.add_anchor("A")
        self.add_anchor("R")

    def get_internal_connections(self):
        """Retorna pares de anchors conectados internamente."""
        if self.body_state == 0:
            return [("A", "R")]
        elif self.body_state == 1:
            return [("P", "A")]