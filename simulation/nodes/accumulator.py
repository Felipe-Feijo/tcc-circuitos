"""Nó de simulação de acumulador hidráulico a gás (lei de Boyle, bexiga)."""

from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin


class Accumulator(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "accumulator", domain=domain, properties=properties)

        for key in ("V0", "P0"):
            if self.properties.get(key) is None:
                raise ValueError(
                    f"Accumulator '{self.id}': propriedade obrigatória '{key}' não preenchida."
                )
        self.V0 = float(self.properties["V0"])
        self.P0 = float(self.properties["P0"])
        self.Vf = 0.0
        self.flow_var = f"Q_{self.id}"

    def _p_gas(self, Vf: float) -> float:
        """Lei de Boyle isotérmica (n=1): P0*V0/(V0-Vf).

        Vf é limitado a V0-EPS antes da divisão -- não é física (a
        equação nunca converge pedindo Vf>=V0-EPS, já que P diverge
        antes), é só para nunca cair em divisão por zero/negativo se Vf
        chegar exatamente em V0 pelo clip de post_step_update.
        """
        EPS = self.V0 * 1e-3
        Vf = min(Vf, self.V0 - EPS)
        return self.P0 * self.V0 / (self.V0 - Vf)

    # ------------------------------------------------------------------
    # Contrato hidráulico
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
        EPS = self.V0 * 1e-3
        if self.Vf <= EPS:
            return {self.flow_var: (0.0, None)}
        return {}

    def hydraulic_ports(self):
        return {"P": self.flow_var}

    def equations(self, x, idx):
        P = x[idx[self.anchors["P"].pressure_var]]
        P_gas = self._p_gas(self.Vf)
        P_scale = max(abs(P_gas), self.p_ref)
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
    # Estado
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
