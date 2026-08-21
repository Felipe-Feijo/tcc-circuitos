"""Simulation node for the 5/2-way directional valve."""

import math

from simulation.nodes.directional_valve.directional_valve import DirectionalValve
from simulation.hydraulic import HydraulicMixin


class Valve_5_2_Ways(DirectionalValve, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "valve_5_2_ways", domain=domain, properties=properties)

        if self.domain == "hydraulic":
            self._init_hydraulic_k(self.properties.get("k"))
            self._flow_vars = {
                port: f"Q_{self.id}_{port}" for port in ("P", "A", "B", "R1", "R2")
            }

    def get_internal_connections(self):
        """Returns pairs of internally connected anchors.

        State 0 (rest):   P->B, A->R1
        State 1 (active): P->A, B->R2
        """
        if self.body_state == 0:
            return [("P", "B"), ("A", "R1")]
        else:
            return [("P", "A"), ("B", "R2")]

    # ------------------------------------------------------------------
    # Hydraulic domain
    # ------------------------------------------------------------------
    # Same scheme as the 4/2-way: five ports always connected in pairs
    # (get_internal_connections()), each pair with its own conservation +
    # turbulent orifice equation.

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
        for port_a, port_b in self.get_internal_connections():
            guess[self._flow_vars[port_a]] = 1.0
            guess[self._flow_vars[port_b]] = -1.0
        return guess

    def hydraulic_ports(self):
        if self.domain != "hydraulic":
            return {}
        return dict(self._flow_vars)

    def equations(self, x, idx):
        Q_scale = max(self.q_ref, 1e-12)
        P_scale = max(self.p_ref, 1e-3)

        eqs = []
        for port_a, port_b in self.get_internal_connections():
            Q_a = x[idx[self._flow_vars[port_a]]]
            Q_b = x[idx[self._flow_vars[port_b]]]
            P_a = x[idx[self.anchors[port_a].pressure_var]]
            P_b = x[idx[self.anchors[port_b].pressure_var]]

            delta_p = P_a - P_b

            eqs.append((Q_a + Q_b) / Q_scale)
            eqs.append((delta_p - math.copysign((Q_a / self.k) ** 2, Q_a)) / P_scale)

        return eqs
