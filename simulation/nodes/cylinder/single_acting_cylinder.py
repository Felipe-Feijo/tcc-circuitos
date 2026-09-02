"""Single-acting cylinder simulation node."""

import math
from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin

class SingleActingCylinder(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "single_acting_cylinder", domain=domain, properties=properties)

        default = self.properties.get("default_state", "retracted")
        self.position = 1 if default == "extended" else 0

        self.sensors = self.properties.get("sensors", {
            "retracted": {"enabled": False, "name": ""},
            "extended":  {"enabled": False, "name": ""}
        })

        self.outputs = {}

        # Initializes sensor outputs from default_state, so the value is
        # already correct before the first simulation step.
        if self.sensors["retracted"]["enabled"]:
            name = self.sensors["retracted"]["name"]
            if name:
                self.outputs[name] = {"type": "signal", "value": self.position == 0}

        if self.sensors["extended"]["enabled"]:
            name = self.sensors["extended"]["name"]
            if name:
                self.outputs[name] = {"type": "signal", "value": self.position == 1}

        if self.domain == "hydraulic":
            for key in ("bore", "stroke", "spring_k"):
                if self.properties.get(key) is None:
                    raise ValueError(
                        f"SingleActingCylinder '{self.id}': required property '{key}' is not set."
                    )
            bore                 = float(self.properties["bore"])
            self.area            = math.pi * (bore / 2) ** 2
            self.stroke          = float(self.properties["stroke"])
            self.spring_k        = float(self.properties["spring_k"])
            self.external_force  = float(self.properties.get("external_force") or 0.0)
            self.friction        = 1e-3   # hidden -- minimum value to close the equation
            stroke_val = float(self.properties["stroke"])
            self.x = stroke_val if default == "extended" else 0.0
            self.flow_var        = f"Q_{self.id}"

            # Spring-damper end stop (internal parameters, not exposed)
            F_worst = max(abs(self.external_force), self.spring_k * self.stroke, 1.0)
            self.k_end = max(
                self.spring_k * 1e4,
                F_worst / (self.stroke * 1e-6),
                1e8,
            )
            self.c_end = 2.0 * math.sqrt(self.k_end * self.area ** 2 / self.friction)

    # ------------------------------------------------------------------
    # End-stop helpers
    # ------------------------------------------------------------------

    def _contact_force(self, x, v) -> float:
        """Contact force at the end stops (always pushes back toward the stroke)."""
        pen_ret = max(0.0, -x)                    # penetration at the retracted stop
        pen_ext = max(0.0, x - self.stroke)       # penetration at the extended stop

        F = 0.0
        if pen_ret > 0:
            F += self.k_end * pen_ret - self.c_end * min(v, 0.0)   # v negative = moving in
        if pen_ext > 0:
            F -= self.k_end * pen_ext - self.c_end * max(v, 0.0)   # v positive = moving in

        return F

    # ------------------------------------------------------------------
    # Hydraulic contract
    # ------------------------------------------------------------------

    @property
    def variables(self):
        if self.domain != "hydraulic":
            return []
        anchor = self.anchors["A"]
        pvar = getattr(anchor, "pressure_var", None) if anchor else None
        return ([pvar] if pvar else []) + [self.flow_var]

    @property
    def is_flow_source(self) -> bool:
        # A compressed spring can expel oil -- a variable flow source.
        return self.x > 0.0

    @property
    def flow_hint(self) -> float:
        # The cylinder isn't a controlled flow source -- q_ref comes from the pump.
        # The "can expel oil" semantics are captured by is_flow_source.
        return 0.0

    @property
    def p_hint(self) -> float:
        F = self.spring_k * self.x + self.external_force
        return F / self.area if self.area > 0 else 0.0

    @property
    def initial_guess(self):
        if self.domain != "hydraulic":
            return {}
        anchor = self.anchors["A"]
        EPS    = self.stroke * 1e-3

        # At an end stop: the physically correct guess is Q=0, since the
        # piston is stationary. Using anchor.pressure here is dangerous
        # -- when the circuit switches topology (a valve commutates),
        # anchor.pressure still carries the previous regime's pressure
        # (e.g. 1.6 MPa from a relief valve), which produces a Q_eq
        # around +1000 m3/s, 8 orders of magnitude above q_ref, with the
        # wrong sign for the bound (Q <= 0). The solver takes 30s to
        # escape that guess. Fix: at the end stops, guess 0 directly.
        # Off the stops, use the spring's p_hint (the real equilibrium
        # pressure), not anchor.pressure.
        if self.x <= EPS or self.x >= self.stroke - EPS:
            return {self.flow_var: 0.0}

        # Free zone: estimates Q from force equilibrium using p_hint (the
        # spring's pressure), which is always physically consistent --
        # doesn't depend on NodeContinuity's history.
        P_eq      = self.p_hint   # F_spring / area -- the spring's equilibrium pressure
        F_spring  = self.spring_k * self.x
        F_net     = P_eq * self.area - F_spring - self.external_force
        Q_eq      = (F_net / max(self.friction, 1e-3)) * self.area
        # clips to +-q_ref so it doesn't blow up if F_net is large for some reason
        q_ref  = getattr(self, "q_ref", 1e-4)
        Q_eq   = max(-q_ref, min(q_ref, Q_eq))
        return {self.flow_var: Q_eq}

    def hydraulic_ports(self):
        if self.domain != "hydraulic":
            return {}
        return {"A": self.flow_var}

    @property
    def bounds(self):
        if self.domain != "hydraulic":
            return {}

        EPS = self.stroke * 1e-3

        if self.x <= EPS:
            return {self.flow_var: (0.0, None)}    # can only extend
        elif self.x >= self.stroke - EPS:
            return {self.flow_var: (None, 0.0)}    # can only retract

        return {}

    def equations(self, x, idx):
        Q = x[idx[self.flow_var]]
        P = x[idx[self.anchors["A"].pressure_var]]
        v = Q / self.area
        F_hidro = P * self.area
        F_res   = self.spring_k * self.x + self.external_force + self.friction * v
        EPS = self.stroke * 1e-3

        if self.x >= self.stroke - EPS:
            # Complementarity: either Q=0 (piston stopped) or F_net=0 (piston moving)
            # P_A is always anchored by the equation -- never left free in NodeContinuity
            a = -Q / self.q_ref                    # >= 0 when Q <= 0
            b = (F_hidro - F_res) / max(F_res, 1)  # >= 0 when pressure sustains it
            return [a + b - math.sqrt(a**2 + b**2)]

        # at the retracted stop with force pushing outward
        if self.x <= EPS and F_hidro <= F_res:
            F_scale = max(abs(F_res), 1.0)
            return [Q / (self.area * F_scale)]  # forces Q -> 0

        # free zone -- normal force equilibrium
        F_contact = self._contact_force(self.x, v)
        F_net   = F_hidro - F_res - F_contact
        F_scale = max(abs(F_hidro), abs(F_res), 1.0)
        return [F_net / F_scale]

    # ------------------------------------------------------------------
    # Logical update
    # ------------------------------------------------------------------

    def update(self, outputs=None):
        if self.domain != "hydraulic":
            self.position = 1 if self.anchors["A"].state else 0

    # ------------------------------------------------------------------
    # Post step
    # ------------------------------------------------------------------

    def post_step_update(self, dt=None):
        super().post_step_update(dt=dt)

        # sensors
        if self.sensors["retracted"]["enabled"]:
            name = self.sensors["retracted"]["name"]
            self.outputs[name] = {"type": "signal", "value": self.position == 0}

        if self.sensors["extended"]["enabled"]:
            name = self.sensors["extended"]["name"]
            self.outputs[name] = {"type": "signal", "value": self.position == 1}

        if self.domain == "hydraulic" and dt is not None:
            anchor = self.anchors["A"]
            if anchor and not isinstance(anchor.flow, str):
                self.x += (anchor.flow / self.area) * dt
                if self.x > self.stroke:
                    self.x = self.stroke
                elif self.x < 0:
                    self.x = 0

                # position: 0 or 1 with a 1% of stroke threshold
                if self.stroke > 0:
                    ratio = self.x / self.stroke
                    if ratio < 0.01:
                        self.position = 0
                    elif ratio > 0.99:
                        self.position = 1
                    else:
                        self.position = round(ratio)


    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_visual_state(self):
        if self.domain == "hydraulic" and self.stroke > 0:
            return max(0.0, min(1.0, self.x / self.stroke))
        return self.position

    def get_state(self):
        state = super().get_state()
        state["position"] = self.position
        if self.domain == "hydraulic":
            state["x"] = self.x
        return state

    def set_state(self, state):
        super().set_state(state)
        self.position = state.get("position", self.position)
        if self.domain == "hydraulic":
            self.x = state.get("x", self.x)