"""Nó de simulação de válvula de alívio de ação direta (sequence valve
quando pilotada — ver properties["piloted"])."""

import math
from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin

class ReliefValve(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "relief_valve", domain=domain, properties=properties)
        if self.domain == "hydraulic":
            p_set = self.properties.get("p_set")
            if p_set is None:
                raise ValueError(f"ReliefValve '{self.id}': propriedade obrigatória 'p_set' não preenchida.")
            self.p_set        = float(p_set)
            self.flow_var_in  = f"Q_{self.id}_in"
            self.flow_var_out = f"Q_{self.id}_out"
            self.piloted = bool(self.properties.get("piloted", False))
            if self.piloted:
                self.flow_var_y = f"Q_{self.id}_Y"

    @property
    def p_hint(self) -> float:
        return self.p_set

    @property
    def variables(self) -> list:
        if self.domain != "hydraulic":
            return []
        vars_ = [self.flow_var_in, self.flow_var_out]
        if self.piloted:
            vars_.append(self.flow_var_y)
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
        ports = {"P": self.flow_var_in, "T": self.flow_var_out}
        if self.piloted:
            ports["Y"] = self.flow_var_y
        return ports

    def equations(self, x, idx):
        Q_in  = x[idx[self.flow_var_in]]
        Q_out = x[idx[self.flow_var_out]]
        P_in  = x[idx[self.anchors["P"].pressure_var]]
        P_out = x[idx[self.anchors["T"].pressure_var]]

        Q_scale = self.q_ref
        P_scale = self.p_ref

        eq_conservation = (Q_in + Q_out) / Q_scale

        if self.piloted:
            P_y = x[idx[self.anchors["Y"].pressure_var]]
            effective_p_set = self.p_set + P_y
        else:
            effective_p_set = self.p_set

        # regime passivo: só entra quando o lado T está genuinamente
        # contrapressurizado acima do próprio limiar efetivo — não apenas
        # acima de P_in. Sem o gate por effective_p_set, P_in e P_out
        # perto de zero (ruído numérico logo após uma mudança de
        # topologia) bastavam para disparar o branch, que não
        # referencia o limiar, e a relief "abria" sem nunca ter atingido
        # a pressão de ajuste.
        if P_out > effective_p_set and P_out >= P_in and Q_in > 0:
            eq_fb = (P_in - P_out) / P_scale
        else:
            a = (effective_p_set - P_in) / P_scale
            b = Q_in / Q_scale
            eq_fb = a + b - math.sqrt(a*a + b*b)

        eqs = [eq_conservation, eq_fb]
        if self.piloted:
            Q_y = x[idx[self.flow_var_y]]
            eqs.append(Q_y / Q_scale)  # porta morta -- só sensoriamento
        return eqs

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

    def set_scale(self, p_ref: float, q_ref: float) -> None:
        self.p_ref = max(p_ref, 1e5)   # mínimo 1 bar — escala realista
        self.q_ref = max(q_ref, 1e-10)