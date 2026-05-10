import math
from simulation.nodes.nodes import Node

class DirectOperatedReliefValve(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "direct_operated_relief_valve", domain=domain, properties=properties)
        if self.domain == "hydraulic":
            self.p_set        = self.properties.get("p_set", 10)
            self.flow_var_in  = f"Q_{self.id}_in"
            self.flow_var_out = f"Q_{self.id}_out"

    @property
    def p_hint(self) -> float:
        return self.p_set
        # anchor_p = self.anchors.get("P")
        # p_hint = anchor_p.pressure if isinstance(anchor_p.pressure, (int, float)) and anchor_p.pressure >= self.p_set else 0.0
        # return p_hint

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

    @property
    def bounds(self):
        return {
            self.flow_var_in: (0.0, None),   # Q_in nunca negativo
            self.flow_var_out: (None, 0.0),  # Q_out nunca positivo
        }

    def hydraulic_ports(self) -> dict:
        if self.domain != "hydraulic":
            return {}
        return {"P": self.flow_var_in, "T": self.flow_var_out}

    def equations(self, x, idx):
        Q_in  = x[idx[self.flow_var_in]]
        Q_out = x[idx[self.flow_var_out]]
        P_in  = x[idx[self.anchors["P"].pressure_var]]
        P_out = x[idx[self.anchors["T"].pressure_var]]

        Q_scale = self.q_ref
        P_scale = self.p_ref

        eq_conservation = (Q_in + Q_out) / Q_scale

        # regime passivo: fluxo reverso de pressão com vazão positiva
        if P_out > P_in and Q_in > 0:
            eq_fb = (P_in - P_out) / P_scale
        else:
            a = (self.p_set - P_in) / P_scale
            b = Q_in / Q_scale
            eq_fb = a + b - math.sqrt(a*a + b*b)

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

    def set_scale(self, p_ref, q_ref):
        self.p_ref = max(p_ref, 1e-3)
        self.q_ref = max(q_ref, 1e-12)