"""Classe base de simulação para válvulas direcionais."""

from simulation.nodes.nodes import Node

class DirectionalValve(Node):
    THREE_POSITION = False

    def __init__(self, node_id: str, node_type: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, node_type, domain=domain, properties=properties)

        # Bits do item gráfico
        self.bits = {"left": 0, "right": 0}

        # Nova estrutura: {"left": {"type": "pilot"}, "right": None}
        self.actuators = self.properties.get("actuators", {"left": None, "right": None})

        if self.THREE_POSITION:
            self.body_state = 1  # repouso é sempre o centro -- default_side não se aplica
        else:
            default_side = self.properties.get("default_side", "right")
            self.body_state = 1 if default_side == "left" else 0

        # Timer actuator state: steps remaining per side (0 = idle)
        self._timer_steps: dict[str, int] = {"left": 0, "right": 0}

        # Defeito injetado durante a simulação (nunca persistido em
        # self.properties -- vive só nesta instância de domínio).
        self._stuck_defect = False

    def handle_command(self, command: dict):
        """
        command:
        type: "actuator"
        side: "left" | "right"
        value: 0 | 1

        Ou, para simulação de defeito:
        action: "set_defect"
        k: float      (novo coeficiente de vazão; só tem efeito em nós que
                        definem self.k -- domínio hidráulico)
        stuck: bool   (True trava o corpo da válvula na posição atual)

        action: "clear_defect"
        (sem outros campos -- restaura k original e destrava)
        """
        action = command.get("action")
        if action == "set_defect":
            self._apply_defect_command(command)
            return
        if action == "clear_defect":
            self._clear_defect()
            return

        if command.get("type") != "actuator":
            return

        side = command.get("side")
        value = command.get("value")

        if side not in self.bits:
            return

        if value not in (0, 1):
            return

        self.bits[side] = value

    def _apply_defect_command(self, command: dict) -> None:
        """Aplica um defeito injetado durante a simulação.

        k só tem efeito em nós hidráulicos (que definem self.k no __init__);
        em domínio pneumático, ou se self.k nunca foi definido, o campo é
        ignorado silenciosamente.
        """
        if hasattr(self, "k"):
            k = command.get("k")
            if k is not None:
                self.k = float(k)
        self._stuck_defect = bool(command.get("stuck", False))

    def _clear_defect(self) -> None:
        """Remove qualquer defeito ativo, restaurando o k original."""
        if hasattr(self, "_k_default"):
            self.k = self._k_default
        self._stuck_defect = False

    @property
    def defect_active(self) -> bool:
        """True se algum defeito estiver ativo (k desviado do original ou travada)."""
        k_default = getattr(self, "_k_default", None)
        k_changed = k_default is not None and getattr(self, "k", k_default) != k_default
        return bool(self._stuck_defect or k_changed)

    def _update_pilots(self):
        for side in ("left", "right"):
            actuator = self.actuators.get(side)
            if not actuator:
                continue
            atype = actuator.get("type")
            anchor_name = "PL" if side == "left" else "PR"
            if atype == "pneumatic_pilot":
                self.bits[side] = 1 if self.anchors[anchor_name].state else 0
            elif atype == "hydraulic_pilot":
                self.bits[side] = 1 if self.anchors[anchor_name].pressure > 1e5 else 0

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
        if self._stuck_defect:
            return  # defeito "válvula travada" -- corpo não reage mais a bits

        left = self.bits["left"]
        right = self.bits["right"]

        if self.THREE_POSITION:
            if left and not right:
                self.body_state = 2
            elif right and not left:
                self.body_state = 0
            else:
                # 00 (repouso) e 11 (pilotos se anulam) -- só a mola atua -> centro
                self.body_state = 1
            return

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