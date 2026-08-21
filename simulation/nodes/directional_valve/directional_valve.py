"""Base simulation class for directional valves."""

from simulation.nodes.nodes import Node

class DirectionalValve(Node):
    THREE_POSITION = False

    def __init__(self, node_id: str, node_type: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, node_type, domain=domain, properties=properties)

        # Graphics item bits
        self.bits = {"left": 0, "right": 0}

        # New structure: {"left": {"type": "pilot"}, "right": None}
        self.actuators = self.properties.get("actuators", {"left": None, "right": None})

        if self.THREE_POSITION:
            self.body_state = 1  # rest is always the center -- default_side doesn't apply
        else:
            default_side = self.properties.get("default_side", "right")
            self.body_state = 1 if default_side == "left" else 0

        # Timer actuator state: steps remaining per side (0 = idle)
        self._timer_steps: dict[str, int] = {"left": 0, "right": 0}

        # Defect injected during simulation (never persisted to
        # self.properties -- lives only in this domain instance).
        self._stuck_defect = False

    def _init_hydraulic_k(self, k) -> None:
        """Validates and stores the hydraulic conductance k.

        Call from inside each hydraulic subclass's __init__, inside the
        `if self.domain == "hydraulic":` guard, with k = self.properties.get("k"):

            if self.domain == "hydraulic":
                self._init_hydraulic_k(self.properties.get("k"))
                self._flow_vars = {...}  # subclass-specific rest

        Besides validating (required, must be numeric) and setting
        self.k, captures the original value in self._k_default -- used
        by defect_active/_clear_defect (defined below, in this base
        class) to restore/detect a k deviated by "Simular defeito...".
        Without this capture, defect_active and _clear_defect silently
        don't work for the subclass (already happened with three of the
        five valves -- 2/2, 4/3 and 5/2 -- before this extraction, from
        setting self.k directly without calling this).
        """
        if k is None:
            raise ValueError(
                f"{type(self).__name__} '{self.id}': required property 'k' is not set."
            )
        self.k = float(k)
        self._k_default = self.k

    def handle_command(self, command: dict):
        """
        command:
        type: "actuator"
        side: "left" | "right"
        value: 0 | 1

        Or, for defect simulation:
        action: "set_defect"
        k: float      (new flow coefficient; only affects nodes that
                        define self.k -- hydraulic domain)
        stuck: bool   (True locks the valve's body at its current position)

        action: "clear_defect"
        (no other fields -- restores the original k and unlocks)
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
        """Applies a defect injected during simulation.

        k only affects hydraulic nodes (which define self.k in __init__);
        in the pneumatic domain, or if self.k was never defined, the
        field is silently ignored.
        """
        if hasattr(self, "k"):
            k = command.get("k")
            if k is not None:
                self.k = float(k)
        self._stuck_defect = bool(command.get("stuck", False))

    def _clear_defect(self) -> None:
        """Clears any active defect, restoring the original k."""
        if hasattr(self, "_k_default"):
            self.k = self._k_default
        self._stuck_defect = False

    @property
    def defect_active(self) -> bool:
        """True if any defect is active (k deviated from the original, or locked)."""
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

            # only acts if the other side isn't forcing
            if not other_actuator or other_actuator.get("type") != "spring":
                self.bits[side] = 0 if self.bits[other] else 1

    def _update_sensor_actuators(self, outputs):
        """
        Updates bits based on sensors wired to the actuators.
        outputs: dict[name, payload]
        """
        for side in ("left", "right"):
            actuator = self.actuators.get(side)
            if not actuator:
                continue

            # for now only limit_switch exists,
            # but this is already ready for other sensors in the future
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
            return  # "stuck valve" defect -- body no longer reacts to bits

        left = self.bits["left"]
        right = self.bits["right"]

        if self.THREE_POSITION:
            if left and not right:
                self.body_state = 2
            elif right and not left:
                self.body_state = 0
            else:
                # 00 (rest) and 11 (pilots cancel out) -- only the spring acts -> center
                self.body_state = 1
            return

        if left and not right:
            self.body_state = 1
        elif right and not left:
            self.body_state = 0
        # 00 and 11 -> unchanged

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
        sensors: optional {sensor_name: bool} dict with sensor states
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