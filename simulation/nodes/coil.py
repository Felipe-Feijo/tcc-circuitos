"""Nó de simulação de bobina elétrica."""

from simulation.nodes.nodes import Node

class Coil(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "coil", domain=domain, properties=properties)

        # Estado interno: 0 = desligado, 1 = energizado
        self.energized = 0

        # Sensor salvo em properties
        self.sensor = self.properties.get("sensor", {}).get("coil", {})

        # Dicionário de outputs
        self.outputs = {}

    def update(self, outputs=None):
        """
        Atualiza estado interno com base na lógica AND das anchors T e B
        """
        self.energized = 1 if (self.anchors["T"].state and self.anchors["B"].state) else 0

    def post_step_update(self, dt):
        """
        Atualiza o sinal de saída do solenoide
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