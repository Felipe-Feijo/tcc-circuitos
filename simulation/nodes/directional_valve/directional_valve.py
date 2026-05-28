"""Classe base de simulação para válvulas direcionais."""

from simulation.nodes.nodes import Node

class DirectionalValve(Node):
    def __init__(self, node_id: str, node_type: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, node_type, domain=domain, properties=properties)

        # Bits do item gráfico
        self.bits = {"left": 0, "right": 0}

        # Nova estrutura: {"left": {"type": "pilot"}, "right": None}
        self.actuators = self.properties.get("actuators", {"left": None, "right": None})

        default_side = self.properties.get("default_side", "right")
        self.body_state = 1 if default_side == "left" else 0

        # Timer actuator state: steps remaining per side (0 = idle)
        self._timer_steps: dict[str, int] = {"left": 0, "right": 0}

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
            self.bits[side] = 1 if self.anchors[anchor].state else 0

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

    def _update_sensor_actuators(self, outputs):
        """
        Atualiza bits baseado em sensores ligados aos atuadores.
        outputs: dict[name, payload]
        """
        for side in ("left", "right"):
            actuator = self.actuators.get(side)
            if not actuator:
                continue

            # por enquanto só existe limit_switch,
            # mas já fica pronto para outros sensores no futuro
            if actuator.get("type") not in ["limit_switch", "solenoid"]:
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

    def _update_timers(self):
        """Reset timer counter if the pilot anchor loses pressure."""
        for side in ("left", "right"):
            actuator = self.actuators.get(side)
            if not actuator or actuator.get("type") != "timer":
                continue
            anchor = "PL" if side == "left" else "PR"
            if not self.anchors[anchor].state:
                # Signal dropped — reset counter and bit
                self._timer_steps[side] = 0
                self.bits[side] = 0

    def post_step_update(self, dt=None):
        """Tick timer counters on stabilised states (once per step)."""
        super().post_step_update(dt=dt)
        for side in ("left", "right"):
            actuator = self.actuators.get(side)
            if not actuator or actuator.get("type") != "timer":
                continue
            anchor = "PL" if side == "left" else "PR"
            if not self.anchors[anchor].state:
                self._timer_steps[side] = 0
                self.bits[side] = 0
                continue
            if self.bits[side] == 1:
                # Already fired — stay active
                continue
            delay = int((self.properties.get("actuators", {}).get(side) or {}).get("delay_steps", 3))
            if self._timer_steps[side] == 0:
                self._timer_steps[side] = delay
            self._timer_steps[side] -= 1
            if self._timer_steps[side] <= 0:
                self._timer_steps[side] = 0
                self.bits[side] = 1
        self._compute_body_state()

    def update(self, outputs=None):
        """
        sensors: dicionário opcional {sensor_name: bool} com estado dos sensores
        """
        self._update_pilots()
        self._update_timers()

        if outputs:
            self._update_sensor_actuators(outputs)

        self._update_springs()

        self._compute_body_state()

    def get_state(self):
        state = super().get_state()
        state.update({
            "bits": self.bits.copy(),
            "body_state": self.body_state,
            "timer_steps": self._timer_steps.copy(),
        })
        return state

    def set_state(self, state):
        super().set_state(state)

        if "bits" in state:
            self.bits = state["bits"].copy()

        if "body_state" in state:
            self.body_state = state["body_state"]

        if "timer_steps" in state:
            self._timer_steps = state["timer_steps"].copy()