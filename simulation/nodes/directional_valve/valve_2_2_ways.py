"""Nó de simulação de válvula direcional 2/2 vias."""

import math

from simulation.nodes.directional_valve.directional_valve import DirectionalValve
from simulation.hydraulic import HydraulicMixin


class Valve_2_2_Ways(DirectionalValve, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "valve_2_2_ways", domain=domain, properties=properties)

        if self.domain == "hydraulic":
            k = self.properties.get("k")
            if k is None:
                raise ValueError(
                    f"Valve_2_2_Ways '{self.id}': propriedade obrigatória 'k' não preenchida."
                )
            self.k = float(k)
            self.flow_var_in  = f"Q_{self.id}_in"
            self.flow_var_out = f"Q_{self.id}_out"

    def get_internal_connections(self):
        """body_state == 1 (ativa): conecta P<->A. body_state == 0 (repouso,
        normalmente fechada): bloqueada, sem conexão nenhuma."""
        if self.body_state == 1:
            return [("P", "A")]
        return []

    # ------------------------------------------------------------------
    # Domínio hidráulico
    # ------------------------------------------------------------------
    # Diferente das 3/2, 4/2 e 5/2 vias (sempre têm algum par de portas
    # conectado, só muda o pareamento), a 2/2 pode ficar genuinamente
    # BLOQUEADA no repouso -- nesse estado não há orifício nem conservação
    # entre P e A, cada porta fica isolada (variables/hydraulic_ports
    # vazios, equations() não contribui equação nenhuma).

    @property
    def variables(self):
        if self.domain != "hydraulic" or self.body_state != 1:
            return []
        vars_ = [self.flow_var_in, self.flow_var_out]
        for anchor_name in self.hydraulic_ports().keys():
            anchor = self.anchors.get(anchor_name)
            if anchor and anchor.pressure_var:
                vars_.append(anchor.pressure_var)
        return vars_

    @property
    def initial_guess(self):
        if self.domain != "hydraulic" or self.body_state != 1:
            return {}
        return {
            self.flow_var_in:  1.0,
            self.flow_var_out: -1.0,
        }

    def hydraulic_ports(self):
        if self.domain != "hydraulic" or self.body_state != 1:
            return {}
        return {
            "P": self.flow_var_in,
            "A": self.flow_var_out,
        }

    def equations(self, x, idx):
        if self.domain != "hydraulic" or self.body_state != 1:
            return []

        Q_in  = x[idx[self.flow_var_in]]
        Q_out = x[idx[self.flow_var_out]]

        P_in  = x[idx[self.anchors["P"].pressure_var]]
        P_out = x[idx[self.anchors["A"].pressure_var]]

        delta_p = P_in - P_out

        Q_scale = max(self.q_ref, 1e-12)
        P_scale = max(self.p_ref, 1e-3)

        eq_flow = (Q_in + Q_out) / Q_scale
        eq_dp = (delta_p - math.copysign((Q_in / self.k) ** 2, Q_in)) / P_scale

        return [eq_flow, eq_dp]

    def set_scale(self, p_ref: float, q_ref: float) -> None:
        self.p_ref = max(p_ref, 1e5)
        self.q_ref = max(q_ref, 1e-10)
