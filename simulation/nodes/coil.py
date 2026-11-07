"""Simulation node for the electrical coil."""

from simulation.nodes.nodes import Node

class Coil(Node):
    # T-B is a load, not a conductor: the engine decides actuation from
    # the voltage across it, not from its anchors being energized.
    is_electric_load = True

    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "coil", domain=domain, properties=properties)

        # Internal state: 0 = off, 1 = energized
        self.energized = 0

        # Set by SimulationEngine: T and B sit at different potentials
        # on some source->ground path.
        self.powered = False

        # Sensor stored in properties
        self.sensor = self.properties.get("sensor", {}).get("coil", {})

        # Outputs dict
        self.outputs = {}

    def update(self, outputs=None):
        """
        Updates internal state from the engine's load decision. Both
        anchors energized isn't enough: a shorted coil has T and B at
        the same potential.
        """
        self.energized = 1 if self.powered else 0

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
        state["powered"] = self.powered
        return state

    def set_state(self, state):
        super().set_state(state)
        self.energized = state.get("energized", self.energized)
        self.powered = state.get("powered", self.powered)

    def get_internal_connections(self):
        return [("T", "B")]
