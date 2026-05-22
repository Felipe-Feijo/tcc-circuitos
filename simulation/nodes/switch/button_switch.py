"""Nó de simulação de chave tipo botão."""

from simulation.nodes.nodes import Node


class ButtonSwitch(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "button_switch", domain=domain, properties=properties)

        self.state = 0  # 0 = repouso, 1 = acionado
        self.contact_type = self.properties.get("contact_type", "NO")

    # --------------------------
    # Comandos vindos da UI
    # --------------------------
    def handle_command(self, command: dict):
        """
        command:
            type: "switch"
            value: 0 | 1
        """
        if command.get("type") != "switch":
            return

        value = command.get("value")
        if value not in (0, 1):
            return

        self.state = value

    # --------------------------
    # Atualização lógica
    # --------------------------
    def update(self, outputs=None):
        """
        Switch é puramente passivo — não depende de sensores.
        """
        pass

    # --------------------------
    # Conexões internas
    # --------------------------
    def get_internal_connections(self):
        """
        Retorna pares de anchors conectados internamente.
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
    # Persistência
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