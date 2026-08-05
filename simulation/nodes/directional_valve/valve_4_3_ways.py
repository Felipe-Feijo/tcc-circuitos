"""Nó de simulação de válvula direcional 4/3 vias, centro fechado."""

import math

from simulation.nodes.directional_valve.directional_valve import DirectionalValve
from simulation.hydraulic import HydraulicMixin


class Valve_4_3_Ways(DirectionalValve, HydraulicMixin):
    THREE_POSITION = True

    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "valve_4_3_ways", domain=domain, properties=properties)

        if self.domain == "hydraulic":
            self._init_hydraulic_k(self.properties.get("k"))
            self._flow_vars = {
                port: f"Q_{self.id}_{port}" for port in ("P", "A", "B", "R")
            }

    def get_internal_connections(self):
        """Retorna pares de anchors conectados internamente.

        Estado 0 (ativo-direita): P→A, B→R
        Estado 1 (centro fechado): nenhum par -- todos os portos bloqueados
        Estado 2 (ativo-esquerda): P→B, A→R
        """
        if self.body_state == 0:
            return [("P", "A"), ("B", "R")]
        elif self.body_state == 2:
            return [("P", "B"), ("A", "R")]
        else:
            return []

    # ------------------------------------------------------------------
    # Domínio hidráulico
    # ------------------------------------------------------------------

    @property
    def variables(self):
        if self.domain != "hydraulic":
            return []
        vars_ = list(self._flow_vars.values())
        for anchor_name in self.hydraulic_ports().keys():
            anchor = self.anchors.get(anchor_name)
            if anchor and anchor.pressure_var:
                vars_.append(anchor.pressure_var)
        return vars_

    @property
    def initial_guess(self):
        if self.domain != "hydraulic":
            return {}
        guess = {}
        pairs = self.get_internal_connections()
        if pairs:
            for port_a, port_b in pairs:
                guess[self._flow_vars[port_a]] = 1.0
                guess[self._flow_vars[port_b]] = -1.0
        else:
            for port in ("P", "A", "B", "R"):
                guess[self._flow_vars[port]] = 0.0
        return guess

    def hydraulic_ports(self):
        if self.domain != "hydraulic":
            return {}
        return dict(self._flow_vars)

    def equations(self, x, idx):
        Q_scale = max(self.q_ref, 1e-12)
        P_scale = max(self.p_ref, 1e-3)

        pairs = self.get_internal_connections()

        if not pairs:
            # Centro fechado: nenhum par conectado -- cada porto tem vazão
            # forçada a zero para manter o sistema bem-posto.
            return [
                x[idx[self._flow_vars[port]]] / Q_scale
                for port in ("P", "A", "B", "R")
            ]

        eqs = []
        for port_a, port_b in pairs:
            Q_a = x[idx[self._flow_vars[port_a]]]
            Q_b = x[idx[self._flow_vars[port_b]]]
            P_a = x[idx[self.anchors[port_a].pressure_var]]
            P_b = x[idx[self.anchors[port_b].pressure_var]]

            delta_p = P_a - P_b

            eqs.append((Q_a + Q_b) / Q_scale)
            eqs.append((delta_p - math.copysign((Q_a / self.k) ** 2, Q_a)) / P_scale)

        return eqs
