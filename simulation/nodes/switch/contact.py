"""Simulation node for a generic NO/NC electric contact.

Merges what used to be two separate node types (ButtonSwitch and
RelaySwitch): the schematic symbol for a contact is the same whatever
actuates it -- a direct click ("Button"), a relay/solenoid coil, or a
cylinder limit switch. "Button" is a sentinel, not a real signal name
(see actuator_sensor / BUTTON_SENSOR in the graphics counterpart).
"""

from simulation.nodes.nodes import Node


class Contact(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "contact", domain=domain, properties=properties)

        self.state = 0  # 0 = at rest, 1 = actuated
        self.actuator_sensor_name = self.properties.get("actuator_sensor")

    # --------------------------
    # Commands coming from the UI
    # --------------------------
    def handle_command(self, command: dict):
        """
        command:
            type: "switch"
            value: 0 | 1

        Meaningful when actuator_sensor is "Button" (direct click instead
        of a named sensor); harmless otherwise -- a sensor-driven contact
        overwrites self.state again on the next update() tick.
        """
        if command.get("type") != "switch":
            return

        value = command.get("value")
        if value not in (0, 1):
            return

        self.state = value

    # --------------------------
    # Logic update
    # --------------------------
    def update(self, outputs=None):

        if not outputs or not self.actuator_sensor_name:
            return
        payload = outputs.get(self.actuator_sensor_name)

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
