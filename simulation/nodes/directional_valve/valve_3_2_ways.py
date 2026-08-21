"""Simulation node for the 3/2-way directional valve."""

import math
from simulation.nodes.directional_valve.directional_valve import DirectionalValve
from simulation.hydraulic import HydraulicMixin

class Valve_3_2_Ways(DirectionalValve, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "valve_3_2_ways", domain=domain, properties=properties)

        if self.domain == "hydraulic":
            self._init_hydraulic_k(self.properties.get("k"))
            self.flow_var_in  = f"Q_{self.id}_in"
            self.flow_var_out = f"Q_{self.id}_out"

    def get_internal_connections(self):
        if self.body_state == 0:
            return [("A", "R")]
        elif self.body_state == 1:
            return [("P", "A")]

    # ------------------------------------------------------------------
    # Hydraulic domain
    # ------------------------------------------------------------------

    @property
    def variables(self):
        vars = [self.flow_var_in, self.flow_var_out]
        for anchor_name in self.hydraulic_ports().keys():
            anchor = self.anchors.get(anchor_name)
            if anchor and anchor.pressure_var:
                vars.append(anchor.pressure_var)
        return vars
    
    @property
    def initial_guess(self):
        if self.domain != "hydraulic":
            return {}
        # sentinels -- will be scaled by the pump's flow_hint
        # opposite sign guarantees Q_in + Q_out = 0 from the start
        return {
            self.flow_var_in:   1.0,
            self.flow_var_out: -1.0,
        }

    def hydraulic_ports(self):
        if self.body_state == 1:  # P → A
            return {
                "P": self.flow_var_in,
                "A": self.flow_var_out,
            }
        else:  # A → R
            return {
                "A": self.flow_var_in,
                "R": self.flow_var_out,
            }


    def equations(self, x, idx):
        Q_in  = x[idx[self.flow_var_in]]
        Q_out = x[idx[self.flow_var_out]]

        if self.body_state == 1:
            P_in  = x[idx[self.anchors["P"].pressure_var]]
            P_out = x[idx[self.anchors["A"].pressure_var]]
        else:
            P_in  = x[idx[self.anchors["A"].pressure_var]]
            P_out = x[idx[self.anchors["R"].pressure_var]]

        delta_p = P_in - P_out

        # ---- global scales (same logic as the rest of the system)
        Q_scale = max(self.q_ref, 1e-12)
        P_scale = max(self.p_ref, 1e-3)

        # ---- equation 1: flow conservation (now STRONG)
        eq_flow = (Q_in + Q_out) / Q_scale

        # ---- equation 2: dP-Q relation (normalized)
        eq_dp = (delta_p - math.copysign((Q_in / self.k) ** 2, Q_in)) / P_scale

        return [eq_flow, eq_dp]


    def set_scale(self, p_ref: float, q_ref: float) -> None:
        self.p_ref = max(p_ref, 1e5)   # minimum 1 bar
        self.q_ref = max(q_ref, 1e-10)
