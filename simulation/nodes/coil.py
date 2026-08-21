"""Simulation node for the electrical coil."""

from simulation.nodes.nodes import Node

class Coil(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "coil", domain=domain, properties=properties)

        # Internal state: 0 = off, 1 = energized
        self.energized = 0

        # Sensor stored in properties
        self.sensor = self.properties.get("sensor", {}).get("coil", {})

        # Outputs dict
        self.outputs = {}

    def update(self, outputs=None):
        """
        Updates internal state based on the AND logic of anchors T and B
        """
        self.energized = 1 if (self.anchors["T"].state and self.anchors["B"].state) else 0

    def post_step_update(self, dt):
        """
        Updates the solenoid's output signal
        """
        if self.sensor.get("name"):
            name = self.sensor["name"]
            self.outputs[name] = {
                "type": "signal",
                "value": bool(self.energized)
            }

    def get_state(self):
        state = super().get_state()
        state["energized"] = self.energized
        return state

    def set_state(self, state):
        super().set_state(state)
        self.energized = state.get("energized", self.energized)

    def get_internal_connections(self):
        return [("T", "B")]