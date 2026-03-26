import math
from simulation.nodes.nodes import Node

class DirectOperatedReliefValve(Node):
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id, "direct_operated_relief_valve", **kwargs)
        if self.domain == "hydraulic":
            self.p_set        = self.properties.get("p_set", 10)
            self.flow_var_in  = f"Q_{self.id}_in"
            self.flow_var_out = f"Q_{self.id}_out"

    @property
    def variables(self) -> list:
        if self.domain != "hydraulic":
            return []
        vars_ = [self.flow_var_in, self.flow_var_out]
        for anchor_name in self.hydraulic_ports().keys():
            anchor = self.anchors.get(anchor_name)
            if anchor and anchor.pressure_var:
                vars_.append(anchor.pressure_var)
        return vars_

    def hydraulic_ports(self) -> dict:
        if self.domain != "hydraulic":
            return {}
        return {"P": self.flow_var_in, "T": self.flow_var_out}

    def equations(self, x, idx) -> list:
        Q_in  = x[idx[self.flow_var_in]]
        Q_out = x[idx[self.flow_var_out]]
        P_in  = x[idx[self.anchors["P"].pressure_var]]
        P_out = x[idx[self.anchors["T"].pressure_var]]

        # Conservação de vazão
        eq_conservation = Q_in + Q_out

        # Fischer-Burmeister: φ(p_set - P_in, Q_in) = 0
        # garante: (p_set - P_in ≥ 0) ⊥ (Q_in ≥ 0)
        # → fechada: Q_in=0, P_in ≤ p_set
        # → aberta:  P_in=p_set, Q_in ≥ 0
        a = self.p_set - P_in
        b = Q_in
        eq_fb = a + b - math.sqrt(a**2 + b**2)

        return [eq_conservation, eq_fb]

    @property
    def initial_guess(self) -> dict:
        if self.domain != "hydraulic":
            return {}
        anchor_p = self.anchors.get("P")
        p_hint = getattr(anchor_p, "pressure", 0.0) if anchor_p else 0.0
        if isinstance(p_hint, str):
            p_hint = 0.0
        return {
            self.flow_var_in:  0.0,
            self.flow_var_out: 0.0,
            self.anchors["P"].pressure_var: p_hint,
        }

    def update(self, outputs=None):
        pass  # sem estado externo — tudo dentro do solver

    def get_state(self):
        return super().get_state()

    def set_state(self, state):
        super().set_state(state)