"""Pilot-operated (two-stage) relief valve with vent / remote-control
port X.

Model (quasi-static), see
docs/superpowers/specs/2026-10-17-pilot-operated-relief-valve-design.md:
  - orifice P -> chamber (turbulent, ThrottleValve form, K_ORIFICE)
  - pilot stage chamber -> T: FB, threshold p_set on P_X
  - main stage P -> T: FB, threshold P_X + p_vent on P_P
Chamber pressure is port X's pressure. X is a real flow port: unconnected,
the engine's per-anchor continuity forces Q_X = 0 (plugged), so no
dead_ports() and no internal pressure variable.

Steady state: P_P = min(p_set, P_remote) + p_vent.
"""

import math
from simulation.nodes.nodes import Node
from simulation.nodes.defect import DefectMixin
from simulation.nodes.param_checks import require_positive
from simulation.hydraulic import HydraulicMixin


def _relief_fb(p_in, p_out, threshold, q, P_scale, Q_scale):
    # A stage can't discharge against an outlet above its setting, so the
    # effective threshold is max(threshold, p_out). Same roots as
    # ReliefValve's passive-regime branch (backpressured: p_in = p_out,
    # q >= 0), but continuous: that branch jumps at q = 0+ and leaves q
    # undetermined, so a stage whose inlet is pinned below p_out (pilot with
    # X vented, T pressurized) converged to arbitrary pilot flow.
    a = (max(threshold, p_out) - p_in) / P_scale
    b = q / Q_scale
    return a + b - math.sqrt(a * a + b * b)


class PilotOperatedReliefValve(DefectMixin, Node, HydraulicMixin):
    # misadjusted pilot spring
    DEFECT_FIELDS = {"p_set": "p_set"}

    K_ORIFICE = 3e-8        # m3/s/sqrt(Pa): ~1 L/min pilot flow at 3 bar
    DEFAULT_P_VENT = 3e5    # Pa, main-poppet spring

    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "pilot_operated_relief_valve", domain=domain, properties=properties)
        if self.domain == "hydraulic":
            p_set = self.properties.get("p_set")
            if p_set is None:
                raise ValueError(f"PilotOperatedReliefValve '{self.id}': required property 'p_set' is not set.")
            self.p_set = float(p_set)
            self.p_vent = float(self.properties.get("p_vent", self.DEFAULT_P_VENT))
            self.validate_params()
            self.flow_var_p = f"Q_{self.id}_P"
            self.flow_var_t = f"Q_{self.id}_T"
            self.flow_var_x = f"Q_{self.id}_X"
            self.flow_var_main = f"Q_{self.id}_main"
            self.flow_var_pilot = f"Q_{self.id}_pilot"

    def validate_params(self) -> None:
        if self.domain == "hydraulic":
            require_positive(self, "p_set", self.p_set)
            require_positive(self, "p_vent", self.p_vent)

    @property
    def p_hint(self) -> float:
        return self.p_set + self.p_vent

    @property
    def variables(self) -> list:
        if self.domain != "hydraulic":
            return []
        vars_ = [self.flow_var_p, self.flow_var_t, self.flow_var_x,
                 self.flow_var_main, self.flow_var_pilot]
        for anchor_name in self.hydraulic_ports().keys():
            anchor = self.anchors.get(anchor_name)
            if anchor and anchor.pressure_var:
                vars_.append(anchor.pressure_var)
        return vars_

    @property
    def bounds(self):
        # Q_P unbounded: with X pressurized above P, pilot oil flows back
        # through the orifice and out of P.
        return {
            self.flow_var_t: (None, 0.0),
            self.flow_var_main: (0.0, None),
            self.flow_var_pilot: (0.0, None),
        }

    def hydraulic_ports(self) -> dict:
        if self.domain != "hydraulic":
            return {}
        return {"P": self.flow_var_p, "T": self.flow_var_t, "X": self.flow_var_x}

    def equations(self, x, idx):
        Q_p = x[idx[self.flow_var_p]]
        Q_t = x[idx[self.flow_var_t]]
        Q_x = x[idx[self.flow_var_x]]
        Q_main = x[idx[self.flow_var_main]]
        Q_pilot = x[idx[self.flow_var_pilot]]
        P_p = x[idx[self.anchors["P"].pressure_var]]
        P_t = x[idx[self.anchors["T"].pressure_var]]
        P_x = x[idx[self.anchors["X"].pressure_var]]

        Q_scale = self.q_ref
        P_scale = self.p_ref

        Q_orif = Q_p - Q_main

        eq_t = (Q_t + Q_main + Q_pilot) / Q_scale
        eq_chamber = (Q_orif - Q_pilot + Q_x) / Q_scale
        eq_orifice = ((P_p - P_x) - math.copysign((Q_orif / self.K_ORIFICE) ** 2, Q_orif)) / P_scale
        eq_pilot = _relief_fb(P_x, P_t, self.p_set, Q_pilot, P_scale, Q_scale)
        eq_main = _relief_fb(P_p, P_t, P_x + self.p_vent, Q_main, P_scale, Q_scale)

        return [eq_t, eq_chamber, eq_orifice, eq_pilot, eq_main]

    @property
    def initial_guess(self) -> dict:
        if self.domain != "hydraulic":
            return {}
        anchor_p = self.anchors.get("P")
        p_hint = getattr(anchor_p, "pressure", 0.0) if anchor_p else 0.0
        if isinstance(p_hint, str):
            p_hint = 0.0
        return {
            self.flow_var_p: 0.0,
            self.flow_var_t: 0.0,
            self.flow_var_x: 0.0,
            self.flow_var_main: 0.0,
            self.flow_var_pilot: 0.0,
            self.anchors["P"].pressure_var: p_hint,
        }

    def update(self, outputs=None):
        pass  # no state of its own

    def set_scale(self, p_ref: float, q_ref: float) -> None:
        self.p_ref = max(p_ref, 1e5)
        self.q_ref = max(q_ref, 1e-10)
