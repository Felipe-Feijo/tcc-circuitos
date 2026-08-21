"""2/2-way directional valve simulation node."""

import math

from simulation.nodes.directional_valve.directional_valve import DirectionalValve
from simulation.hydraulic import HydraulicMixin


class Valve_2_2_Ways(DirectionalValve, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "valve_2_2_ways", domain=domain, properties=properties)

        if self.domain == "hydraulic":
            self._init_hydraulic_k(self.properties.get("k"))
            self.flow_var_in  = f"Q_{self.id}_in"
            self.flow_var_out = f"Q_{self.id}_out"

    def get_internal_connections(self):
        """body_state == 1 (active): connects P<->A. body_state == 0 (rest,
        normally closed): blocked, no connection at all."""
        if self.body_state == 1:
            return [("P", "A")]
        return []

    # ------------------------------------------------------------------
    # Hydraulic domain
    # ------------------------------------------------------------------
    # Unlike the 3/2, 4/2 and 5/2-way valves (always have some port pair
    # connected, only the pairing changes), the 2/2-way can genuinely be
    # BLOCKED at rest -- in that state there's no orifice or conservation
    # between P and A, each port stays isolated (variables/hydraulic_ports
    # empty, equations() contributes no equation at all).

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
