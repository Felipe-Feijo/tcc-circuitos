from simulation.nodes.nodes import Node

class DirectionalValve(Node):
    def __init__(self, node_id, node_type, **kwargs):
        super().__init__(node_id, node_type, **kwargs)

        # Anchors
        self.add_anchor("PL")
        self.add_anchor("PR")

        # Bits do item gráfico
        self.bits = {"left": 0, "right": 0}

        # Nova estrutura: {"left": {"type": "pilot"}, "right": None}
        self.actuators = self.properties.get("actuators", {"left": None, "right": None})

        self.body_state = 0  # 0 = repouso, 1 = ativo

    def handle_command(self, command: dict):
        """
        command:
        type: "actuator"
        side: "left" | "right"
        value: 0 | 1
        """

        if command.get("type") != "actuator":
            return

        side = command.get("side")
        value = command.get("value")

        if side not in self.bits:
            return

        if value not in (0, 1):
            return

        self.bits[side] = value

    def _update_pilots(self):
        for side in ("left", "right"):
            actuator = self.actuators.get(side)
            if not actuator or actuator.get("type") != "pilot":
                continue

            anchor = "PL" if side == "left" else "PR"
            self.bits[side] = 1 if self.anchors[anchor].pressurized else 0

    def _update_springs(self):
        for side in ("left", "right"):
            actuator = self.actuators.get(side)
            if not actuator or actuator.get("type") != "spring":
                continue

            other = "right" if side == "left" else "left"
            other_actuator = self.actuators.get(other)

            # só atua se o outro lado não estiver forçando
            if not other_actuator or other_actuator.get("type") != "spring":
                self.bits[side] = 0 if self.bits[other] else 1

    def _update_limit_switches(self, outputs):
        """
        Atualiza bits baseado nos limit switches.
        outputs: dict[name, payload]
        """
        for side in ("left", "right"):
            actuator = self.actuators.get(side)
            if not actuator or actuator.get("type") != "limit_switch":
                continue

            name = actuator.get("sensor_name")
            payload = outputs.get(name)

            if not payload:
                continue

            if payload.get("type") != "signal":
                continue

            self.bits[side] = 1 if payload.get("value") else 0

    def _compute_body_state(self):
        left = self.bits["left"]
        right = self.bits["right"]

        if left and not right:
            self.body_state = 1
        elif right and not left:
            self.body_state = 0
        # 00 e 11 → mantém

    def update(self, outputs=None):
        """
        sensors: dicionário opcional {sensor_name: bool} com estado dos sensores
        """
        self._update_pilots()
        
        if outputs:
            self._update_limit_switches(outputs)

        self._update_springs()
        
        self._compute_body_state()

    def get_state(self):
        state = super().get_state()
        state.update({
            "bits": self.bits.copy(),
            "body_state": self.body_state
        })
        return state

    def set_state(self, state):
        super().set_state(state)

        if "bits" in state:
            self.bits = state["bits"].copy()

        if "body_state" in state:
            self.body_state = state["body_state"]