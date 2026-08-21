"""Direct-operated relief valve simulation node (a sequence valve when
piloted -- see properties["piloted"])."""

import math
from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin

class ReliefValve(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "relief_valve", domain=domain, properties=properties)
        if self.domain == "hydraulic":
            p_set = self.properties.get("p_set")
            if p_set is None:
                raise ValueError(f"ReliefValve '{self.id}': required property 'p_set' is not set.")
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
            self.flow_var_in: (0.0, None),   # Q_in never negative
            self.flow_var_out: (None, 0.0),  # Q_out never positive
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
            y_anchor = self.anchors.get("Y")
            if y_anchor is None or not y_anchor.connections:
                raise ValueError(
                    f"ReliefValve '{self.id}': piloted port 'Y' is not connected to anything -- "
                    "connect Y to a pressure reference or disable piloting."
                )
            P_y = x[idx[y_anchor.pressure_var]]
            effective_p_set = self.p_set + P_y
        else:
            effective_p_set = self.p_set

        # passive regime: only kicks in when the T side is genuinely
        # backpressurized above its own effective threshold -- not just
        # above P_in. Without the effective_p_set gate, P_in and P_out
        # near zero (numerical noise right after a topology change) was
        # enough to trigger this branch, which doesn't reference the
        # threshold, and the relief valve would "open" without ever
        # having reached the set pressure.
        if P_out > effective_p_set and P_out >= P_in and Q_in > 0:
            eq_fb = (P_in - P_out) / P_scale
        else:
            a = (effective_p_set - P_in) / P_scale
            b = Q_in / Q_scale
            eq_fb = a + b - math.sqrt(a*a + b*b)

        eqs = [eq_conservation, eq_fb]
        if self.piloted:
            Q_y = x[idx[self.flow_var_y]]
            eqs.append(Q_y / Q_scale)  # dead port -- sensing only
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
        pass  # no external state -- everything lives inside the solver

    def get_state(self):
        return super().get_state()

    def set_state(self, state):
        super().set_state(state)

    def set_scale(self, p_ref: float, q_ref: float) -> None:
        self.p_ref = max(p_ref, 1e5)   # minimum 1 bar -- realistic scale
        self.q_ref = max(q_ref, 1e-10)