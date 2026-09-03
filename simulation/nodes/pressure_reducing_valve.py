"""Single-stage, direct-acting pressure reducing valve simulation node.

Normally open -- throttles its own P->A passage to hold the OUTLET
pressure at p_set, and never boosts pressure. No tank port by default:
unlike ReliefValve (simulation/nodes/relief_valve.py), which shunts
excess flow to a T port when the INLET pressure exceeds its threshold,
this valve is in series and simply restricts its own orifice. Modeled
with the same Fischer-Burmeister smoothed complementarity ReliefValve
and CheckValve already use, mirrored to sense P_A (outlet) instead of
P_in.

A third, closed regime is handled outside that FB pairing: if the
outlet is already above p_set (e.g. from external backpressure, or a
stale post-topology-change seed) while forward flow is at or below its
zero lower bound, the FB pairing has no root, so equations() instead
pins Q_P to zero directly.

Optional property `relieving` (default False, mirrors ReliefValve's
`piloted`) adds a real flow port `T`: instead of merely refusing more
inflow while the outlet floats above p_set, the valve actively pulls
P_A back down to p_set via T -- the user wires T to a Reservoir node,
same as any other tank port in this codebase. This is NOT modeled as a
second, independent Fischer-Burmeister pair against (P_A - p_set): that
pairing is satisfied by the same condition (P_A == p_set) as the
supply-side pair, with nothing to decide which port does the work,
making the system rank-deficient exactly at the most commonly visited
state. Instead, the same closed-regime branch above is extended: once
inside it, Q_P stays pinned to zero (as before) and a second equation
directly pins P_A to p_set via T's flow. Outside that branch, T is a
dead port (pinned to zero flow) -- no relief is needed.

`relieving=True` also makes port A BIDIRECTIONAL. With the domain sign
convention (Q > 0 means fluid entering the node through that port), the
2-port valve only ever pushes fluid OUT through A, so Q_A is bounded
(None, 0.0). Relieving reverses that flow: fluid enters at A (something
external pressurizing the outlet) and leaves at T, which requires
Q_A > 0. Keeping the (None, 0.0) bound while relieving makes relief
impossible -- with Q_P pinned to zero and Q_T <= 0, conservation
(Q_P + Q_A + Q_T = 0) forces Q_A = -Q_T with both <= 0, whose only
solution is Q_A = Q_T = 0. So `bounds` drops A's upper bound entirely
when relieving, and keeps it only in the 2-port case.
"""

import math
from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin


class PressureReducingValve(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "pressure_reducing_valve", domain=domain, properties=properties)
        if self.domain == "hydraulic":
            p_set = self.properties.get("p_set")
            if p_set is None:
                raise ValueError(f"PressureReducingValve '{self.id}': required property 'p_set' is not set.")
            self.p_set        = float(p_set)
            self.flow_var_p   = f"Q_{self.id}_P"
            self.flow_var_a   = f"Q_{self.id}_A"
            self.relieving = bool(self.properties.get("relieving", False))
            if self.relieving:
                self.flow_var_t = f"Q_{self.id}_T"

    @property
    def p_hint(self) -> float:
        return self.p_set

    @property
    def variables(self) -> list:
        if self.domain != "hydraulic":
            return []
        vars_ = [self.flow_var_p, self.flow_var_a]
        if self.relieving:
            vars_.append(self.flow_var_t)
        for anchor_name in self.hydraulic_ports().keys():
            anchor = self.anchors.get(anchor_name)
            if anchor and anchor.pressure_var:
                vars_.append(anchor.pressure_var)
        return vars_

    @property
    def bounds(self):
        b = {
            self.flow_var_p: (0.0, None),   # Q_P never negative -- forward flow only
        }
        if self.relieving:
            b[self.flow_var_a] = (None, None)  # A is bidirectional once T can relieve
            b[self.flow_var_t] = (None, 0.0)   # Q_T never positive -- only leaves via T
        else:
            b[self.flow_var_a] = (None, 0.0)   # Q_A never positive -- 2-port, forward only
        return b

    def hydraulic_ports(self) -> dict:
        if self.domain != "hydraulic":
            return {}
        ports = {"P": self.flow_var_p, "A": self.flow_var_a}
        if self.relieving:
            ports["T"] = self.flow_var_t
        return ports

    def equations(self, x, idx):
        Q_p = x[idx[self.flow_var_p]]
        Q_a = x[idx[self.flow_var_a]]
        P_p = x[idx[self.anchors["P"].pressure_var]]
        P_a = x[idx[self.anchors["A"].pressure_var]]

        Q_scale = self.q_ref
        P_scale = self.p_ref

        if self.relieving:
            Q_t = x[idx[self.flow_var_t]]
            eq_conservation = (Q_p + Q_a + Q_t) / Q_scale
        else:
            eq_conservation = (Q_p + Q_a) / Q_scale

        if P_a > self.p_set and Q_p <= 0:
            # Closed: outlet already above setpoint from something this
            # valve cannot supply (external backpressure, or a stale
            # solver seed right after a topology change) and there is no
            # forward flow trying to happen. The 2-regime FB below has no
            # root here (a = p_set - P_a stays negative regardless of b),
            # which would otherwise fault the whole circuit for a state a
            # real valve handles by simply staying shut. Pin Q_p to
            # exactly zero instead of forcing the (infeasible) FB pairing.
            eq_supply = Q_p / Q_scale
            if self.relieving:
                # Actively pull the outlet back down via T instead of
                # leaving it floating above p_set. Flow reverses through
                # A here (Q_a > 0, fluid entering) and leaves via T
                # (Q_t < 0) -- which is why `bounds` drops A's upper
                # bound when relieving, see the module docstring.
                eq_relief = (P_a - self.p_set) / P_scale
        else:
            # a >= 0: P_A never exceeds p_set. b >= 0: the valve only drops
            # pressure (P_P >= P_A), never boosts it. Exactly one is zero:
            # either fully open (b=0, P_A=P_P) or regulating (a=0, P_A=p_set).
            a = (self.p_set - P_a) / P_scale
            b = (P_p - P_a) / P_scale
            eq_supply = a + b - math.sqrt(a * a + b * b)
            if self.relieving:
                eq_relief = Q_t / Q_scale  # dead port here -- no relief needed

        if self.relieving:
            return [eq_conservation, eq_supply, eq_relief]
        return [eq_conservation, eq_supply]

    @property
    def initial_guess(self) -> dict:
        if self.domain != "hydraulic":
            return {}
        anchor_p = self.anchors.get("P")
        p_hint = getattr(anchor_p, "pressure", 0.0) if anchor_p else 0.0
        if isinstance(p_hint, str):
            p_hint = 0.0
        guess = {
            self.flow_var_p: 0.0,
            self.flow_var_a: 0.0,
            self.anchors["P"].pressure_var: p_hint,
        }
        if self.relieving:
            guess[self.flow_var_t] = 0.0
        return guess

    def update(self, outputs=None):
        pass  # no external state -- everything lives inside the solver

    def set_scale(self, p_ref: float, q_ref: float) -> None:
        self.p_ref = max(p_ref, 1e5)    # minimum 1 bar -- realistic scale
        self.q_ref = max(q_ref, 1e-10)
