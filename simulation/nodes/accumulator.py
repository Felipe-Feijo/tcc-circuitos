"""Gas-charged hydraulic accumulator simulation node (Boyle's law, bladder)."""

import math

from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin


class Accumulator(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "accumulator", domain=domain, properties=properties)

        for key in ("V0", "P0"):
            if self.properties.get(key) is None:
                raise ValueError(
                    f"Accumulator '{self.id}': required property '{key}' is not set."
                )
        self.V0 = float(self.properties["V0"])
        self.P0 = float(self.properties["P0"])
        self.Vf = 0.0
        self.flow_var = f"Q_{self.id}"

    @property
    def _eps(self) -> float:
        """Safety margin at both end stops (empty and full), as a fraction of V0."""
        return self.V0 * 1e-3

    def _p_gas(self, Vf: float) -> float:
        """Isothermal Boyle's law (n=1): P0*V0/(V0-Vf).

        Vf is clamped to V0-EPS before the division -- not physical (the
        equation never converges asking for Vf>=V0-EPS, since P diverges
        first), it's just to never hit a division by zero/negative if Vf
        reaches exactly V0 via post_step_update's clip.
        """
        Vf = min(Vf, self.V0 - self._eps)
        return self.P0 * self.V0 / (self.V0 - Vf)

    # ------------------------------------------------------------------
    # Hydraulic contract
    # ------------------------------------------------------------------

    @property
    def variables(self):
        anchor = self.anchors.get("P")
        pvar = getattr(anchor, "pressure_var", None) if anchor else None
        return ([pvar] if pvar else []) + [self.flow_var]

    @property
    def p_hint(self) -> float:
        return self._p_gas(self.Vf)

    @property
    def bounds(self):
        EPS = self._eps
        if self.Vf <= EPS:
            return {self.flow_var: (0.0, None)}
        if self.Vf >= self.V0 - EPS:
            return {self.flow_var: (None, 0.0)}
        return {}

    def hydraulic_ports(self):
        return {"P": self.flow_var}

    def equations(self, x, idx):
        Q = x[idx[self.flow_var]]
        P = x[idx[self.anchors["P"].pressure_var]]
        P_gas = self._p_gas(self.Vf)
        P_scale = max(abs(P_gas), self.p_ref)
        EPS = self._eps

        if self.Vf <= EPS:
            # Empty end stop: smooth complementarity (Fischer-Burmeister),
            # same pattern as single_acting_cylinder.py -- either the
            # accumulator receives no fluid (Q=0, the rest of the circuit's
            # pressure is free to stay below P0) or the circuit's
            # pressure reaches P0 and fluid starts entering (P=P0).
            # Without this, an unconditional P=P_gas(Vf) locked up the
            # solver whenever the rest of the circuit couldn't sustain P0
            # (e.g. an idle accumulator connected only to a reservoir at P=0).
            a = Q / self.q_ref
            b = (P_gas - P) / P_scale
            return [a + b - math.sqrt(a * a + b * b)]

        if self.Vf >= self.V0 - EPS:
            # Full end stop, mirrored: either the accumulator stops
            # receiving fluid (Q<=0, can give it back) or the circuit's
            # pressure reaches P_gas (already huge, clamped by _p_gas).
            # Without this, near full the equation demanded a pressure
            # the rest of the circuit couldn't sustain -- real symptom:
            # Vf oscillating between full and nearly-empty from one step to the next.
            a = -Q / self.q_ref
            b = (P_gas - P) / P_scale
            return [a + b - math.sqrt(a * a + b * b)]

        return [(P - P_gas) / P_scale]

    # ------------------------------------------------------------------
    # Post step
    # ------------------------------------------------------------------

    def post_step_update(self, dt=None):
        super().post_step_update(dt=dt)
        if dt is None:
            return
        anchor = self.anchors["P"]
        if anchor and not isinstance(anchor.flow, str):
            self.Vf += anchor.flow * dt
            self.Vf = max(0.0, min(self.V0, self.Vf))

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_visual_state(self):
        return max(0.0, min(1.0, self.Vf / self.V0)) if self.V0 > 0 else 0.0

    def get_state(self):
        state = super().get_state()
        state["Vf"] = self.Vf
        return state

    def set_state(self, state):
        super().set_state(state)
        self.Vf = state.get("Vf", self.Vf)
