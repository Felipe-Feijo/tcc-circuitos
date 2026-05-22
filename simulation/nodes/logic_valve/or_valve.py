"""Nó de simulação de válvula lógica OR."""

from simulation.nodes.nodes import Node

class OrValve(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "or_valve", domain=domain, properties=properties)

        # Estado interno (shuttle com memória)
        self.active_input: str = "X"  # estado inicial

    def update(self, outputs=None):
        x = self.anchors["X"].state
        y = self.anchors["Y"].state

        # Só muda se exatamente uma entrada estiver pressurizada
        if x ^ y:
            self.active_input = "X" if x else "Y"
        # else: mantém o estado atual

    def get_internal_connections(self):
        return [(self.active_input, "A")]
    
    def get_visual_state(self):
        return self.active_input  # "X" ou "Y"
    

    def get_state(self):
        state = super().get_state()
        state["active_input"] = self.active_input
        return state

    def set_state(self, state):
        super().set_state(state)
        self.active_input = state.get("active_input", self.active_input)