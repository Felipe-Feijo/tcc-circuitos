"""Simulation node for the throttle valve (hydraulic only, fixed orifice).

A plain flow restrictor: two anchors X and Y, a single fixed orifice
between them -- unlike ThrottleCheckValve
(simulation/nodes/check_valve/throttle_check_valve.py), there's no
free-flow direction and no check function. Both directions go through
the exact same turbulent-orifice equation (same form Valve_2_2_Ways
uses for its P/A ports):

    Q_conservation: Q_X + Q_Y = 0
    (P_X - P_Y) = copysign((Q_X / k)^2, Q_X)

`k` (conductance) is required, from properties["k"].

No state of its own and no visual state -- the graphics item
(graphics/items/base/nodes/throttle_valve.py) uses a single static
sprite, nothing to latch each step.
"""

from __future__ import annotations

import math

from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin


class ThrottleValve(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "throttle_valve", domain=domain, properties=properties)

        k = self.properties.get("k")
        if k is None:
            raise ValueError(
                f"ThrottleValve '{self.id}': required property 'k' is not set."
            )
        self.k = float(k)
        self.flow_var_x = f"Q_{self.id}_X"
        self.flow_var_y = f"Q_{self.id}_Y"

    @property
    def variables(self):
        vars_ = [self.flow_var_x, self.flow_var_y]
        for anchor_name in self.hydraulic_ports().keys():
            anchor = self.anchors.get(anchor_name)
            if anchor and anchor.pressure_var:
                vars_.append(anchor.pressure_var)
        return vars_

    def hydraulic_ports(self):
        return {"X": self.flow_var_x, "Y": self.flow_var_y}

    @property
    def initial_guess(self):
        return {self.flow_var_x: 1.0, self.flow_var_y: -1.0}

    def equations(self, x, idx):
        Q_x = x[idx[self.flow_var_x]]
        Q_y = x[idx[self.flow_var_y]]
        P_x = x[idx[self.anchors["X"].pressure_var]]
        P_y = x[idx[self.anchors["Y"].pressure_var]]

        Q_scale = max(self.q_ref, 1e-12)
        P_scale = max(self.p_ref, 1e-3)

        eq_conservation = (Q_x + Q_y) / Q_scale
        eq_orifice = ((P_x - P_y) - math.copysign((Q_x / self.k) ** 2, Q_x)) / P_scale

        return [eq_conservation, eq_orifice]
