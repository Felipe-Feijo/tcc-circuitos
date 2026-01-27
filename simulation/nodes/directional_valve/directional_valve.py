from simulation.nodes.nodes import Node

class DirectionalValve(Node):
    def __init__(self, node_id, node_type, actuators=None):
        super().__init__(node_id, node_type)

        # Anchors
        self.add_anchor("PL")
        self.add_anchor("PR")

        # Bits do item gráfico
        self.bits = {"left": 0, "right": 0}

        self.actuators = actuators or {}

        self.body_state = 0  # 0 = repouso, 1 = ativo

    def handle_command(self, command: dict):
        """
        command: 'press' ou 'release'
        side: 'left' ou 'right'
        """

        if command["type"] == "button":
            if command["side"] not in self.bits:
                return

            if command["action"] == "press":
                self.bits[command["side"]] = 1
            elif command["action"] == "release":
                self.bits[command["side"]] = 0

    def _update_pilots(self):
        for side, actuators in self.actuators.items():
            if not actuators or "pilot" not in actuators:
                continue

            anchor = "PL" if side == "left" else "PR"
            self.bits[side] = 1 if self.anchors[anchor].pressurized else 0

    def _update_springs(self):
        for side, actuators in self.actuators.items():
            if not actuators or "spring" not in actuators:
                continue

            other = "right" if side == "left" else "left"

            if "spring" not in (self.actuators.get(other) or []):
                # só atua se o outro lado não estiver forçando
                self.bits[side] = 0 if self.bits[other] else 1

    def _compute_body_state(self):
        left = self.bits["left"]
        right = self.bits["right"]

        if left and not right:
            self.body_state = 1
        elif right and not left:
            self.body_state = 0
        # 00 e 11 → mantém


    def update(self):
        self._update_pilots()
        self._update_springs()
        self._compute_body_state()


        