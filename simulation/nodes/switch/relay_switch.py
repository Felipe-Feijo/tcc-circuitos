"""Simulation node for the relay contact."""

from simulation.nodes.nodes import Node


class RelaySwitch(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "relay_switch", domain=domain, properties=properties)

        self.state = 0  # 0 = at rest, 1 = actuated
        self.relay_sensor_name = self.properties.get("relay_sensor")

    # --------------------------
    # Logic update
    # --------------------------
    def update(self, outputs=None):

        if not outputs or not self.relay_sensor_name:
            return
        payload = outputs.get(self.relay_sensor_name)

        if not payload:
            return

        if payload.get("type") != "signal":
            return

        self.state = 1 if payload.get("value") else 0

    # --------------------------
    # Internal connections
    # --------------------------
    def get_internal_connections(self):
        """
        Returns pairs of internally connected anchors.
        """

        contact_type = self.properties.get("contact_type", "NO")

        if contact_type == "NO":
            closed = self.state == 1
        else:  # NC
            closed = self.state == 0

        if closed:
            return [("T", "B")]

        return []

    # --------------------------
    # Persistence
    # --------------------------
    def get_state(self):
        state = super().get_state()
        state.update({
            "state": self.state
        })
        return state

    def set_state(self, state):
        super().set_state(state)

        if "state" in state:
            self.state = state["state"]