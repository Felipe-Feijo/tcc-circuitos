"""Simulation node for the AND logic valve."""

from simulation.nodes.nodes import Node

class AndValve(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "and_valve", domain=domain, properties=properties)

        # Internal state (shuttle with memory)
        self.active_input: str = "default"  # initial state

    def update(self, outputs=None):
        x = self.anchors["X"].state
        y = self.anchors["Y"].state

        # Only changes if exactly one input is pressurized
        if x == y and x and y:
            self.active_input = "default"
        elif x != y:
            self.active_input = "X" if x else "Y"
        # else: keeps the current state

    def get_internal_connections(self):
        if self.active_input == "default" and self.anchors["X"].state and self.anchors["Y"].state:
            return [("X", "A"), ("Y", "A")]
        else:
            return []
    
    def get_visual_state(self):
        return self.active_input  # "X" or "Y"
    

    def get_state(self):
        state = super().get_state()
        state["active_input"] = self.active_input
        return state

    def set_state(self, state):
        super().set_state(state)
        self.active_input = state.get("active_input", self.active_input)