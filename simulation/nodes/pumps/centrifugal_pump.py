"""Centrifugal pump simulation node (hydraulic domain).

Unlike the fixed-displacement pump (flow always locked at Q_set), the
centrifugal pump follows a continuous characteristic curve relating
pressure drop and flow -- no branching at all, it's a single equation
valid at any point:

    dp = P_at_P - P_at_S
    dp = H_shutoff * (1 - (Q_S / Q_max)^2)

At Q_S=0 (deadheaded, no flow): dp = H_shutoff (shutoff pressure).
At Q_S=Q_max (free flow, no load): dp = 0.

The parabola only has a real solution for dp <= H_shutoff (its maximum,
at Q_S=0) -- `bounds` locks Q_S to [0, Q_max] so a backpressure beyond
shutoff results in zero flow (the nearest reachable point), not a
spurious negative flow (there'd be no real root to find without this limit).

Sign convention (node_protocol.py: Q>0 = entering the component): S
(suction, bottom of the sprite) is positive -- fluid enters there; P
(discharge, top) is negative -- fluid exits there. Same convention, same
ports and same sprite (only the circle's drawing differs) as
FixedDisplacementPump.

Unlike that one, the variable names here are already tied directly to
the port name (flow_var_p, flow_var_s) -- not "in"/"out", which just
caused needless confusion in this class's sibling.
"""

from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin


class CentrifugalPump(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "centrifugal_pump", domain=domain, properties=properties)

        if self.domain == "hydraulic":
            h_shutoff = self.properties.get("H_shutoff")
            if h_shutoff is None:
                raise ValueError(
                    f"CentrifugalPump '{self.id}': required property 'H_shutoff' is not set."
                )
            q_max = self.properties.get("Q_max")
            if q_max is None:
                raise ValueError(
                    f"CentrifugalPump '{self.id}': required property 'Q_max' is not set."
                )
            self.H_shutoff = float(h_shutoff)
            self.Q_max = float(q_max)
            self.flow_var_p = f"Q_{self.id}_P"
            self.flow_var_s = f"Q_{self.id}_S"

    @property
    def is_flow_source(self) -> bool:
        return True

    @property
    def flow_hint(self) -> float:
        return self.Q_max

    @property
    def p_hint(self) -> float:
        return self.H_shutoff

    @property
    def variables(self):
        return [self.flow_var_p, self.flow_var_s]

    @property
    def bounds(self):
        # The curve dp=H_shutoff*(1-(Q_S/Q_max)^2) only has a real
        # solution for dp <= H_shutoff (the parabola's maximum, at
        # Q_S=0) -- without limits, a backpressure beyond shutoff has no
        # root at all, and the solver can slip into a negative flow
        # trying to find one. Limiting to the valid operating envelope
        # (0 <= Q_S <= Q_max), the nearest reachable point when
        # backpressure exceeds shutoff lands at Q_S=0 -- flow locks at
        # zero, the expected physical behavior (the pump doesn't
        # overcome the backpressure, it doesn't start spinning in
        # reverse on its own).
        return {
            self.flow_var_s: (0.0, self.Q_max),
            self.flow_var_p: (-self.Q_max, 0.0),
        }

    @property
    def initial_guess(self):
        return {
            self.flow_var_p: -self.Q_max / 2,
            self.flow_var_s:  self.Q_max / 2,
        }

    def hydraulic_ports(self):
        return {
            "P": self.flow_var_p,
            "S": self.flow_var_s,
        }

    def equations(self, x, idx):
        Q_p = x[idx[self.flow_var_p]]
        Q_s = x[idx[self.flow_var_s]]

        P_p = x[idx[self.anchors["P"].pressure_var]]
        P_s = x[idx[self.anchors["S"].pressure_var]]

        Q_scale = max(self.q_ref, 1e-12)
        P_scale = max(self.p_ref, 1e-3)

        delta_p = P_p - P_s
        curve = self.H_shutoff * (1 - (Q_s / self.Q_max) ** 2)

        eq_conservation = (Q_p + Q_s) / Q_scale
        eq_curve = (delta_p - curve) / P_scale

        return [eq_conservation, eq_curve]
