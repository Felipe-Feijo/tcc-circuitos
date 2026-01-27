
from simulation.nodes.directional_valve.directional_valve import DirectionalValve


class Valve_4_2_Ways(DirectionalValve):
    def __init__(self, node_id, actuators=None):
        super().__init__(node_id, "valve_4_2_ways", actuators)

        # Anchors
        self.add_anchor("P")
        self.add_anchor("A")
        self.add_anchor("B")
        self.add_anchor("R")

    def get_internal_connections(self):
        """Retorna pares de anchors conectados internamente."""
        if self.body_state == 0:
            return [("P", "A"), ("B", "R")]
        else:
            return [("P", "B"), ("A", "R")]
        