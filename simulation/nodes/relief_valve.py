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
    def p_hint(self) -> float:
        return self.p_set

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
            self.flow_var_in:  (0.0, None),  # 🔥 não permite fluxo reverso
            self.flow_var_out: (None, 0.0)
        }

    def hydraulic_ports(self) -> dict:
        if self.domain != "hydraulic":
            return {}
        return {"P": self.flow_var_in, "T": self.flow_var_out}
    
    def _fb(self, a, b):
        """FB normalizada — evita insensibilidade quando a >> b"""
        norm = max(abs(a), abs(b), 1.0)
        a_n, b_n = a / norm, b / norm
        return (a_n + b_n - math.sqrt(a_n**2 + b_n**2)) * norm

    def equations(self, x, idx):
        Q_in  = x[idx[self.flow_var_in]]
        Q_out = x[idx[self.flow_var_out]]
        P_in  = x[idx[self.anchors["P"].pressure_var]]

        eq_conservation = Q_in + Q_out

        # normaliza cada argumento pela sua própria escala
        p_scale = max(self.p_set, 1.0)
        q_scale = max(Q_in, 1e-12)  # escala dinâmica — o próprio Q atual

        a = (self.p_set - P_in) / p_scale   # adimensional, ~[-1, 1]
        b = Q_in / q_scale                  # adimensional, ~[-1, 0]

        eq_open = self._fb(a, b)

        return [eq_conservation, eq_open]

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