"""Single-stage, direct-acting pressure reducing valve simulation node.

Normally open -- throttles its own P->A passage to hold the OUTLET
pressure at p_set, and never boosts pressure. Modeled with the same
Fischer-Burmeister smoothed complementarity ReliefValve and CheckValve
already use, mirrored to sense P_A (outlet) instead of P_in.

Optional property `relieving` (default False, mirrors ReliefValve's
`piloted`) adds a real flow port `T`: when the supply side alone can't
prevent the outlet from exceeding p_set (a fixed-flow pump forcing more
into P than the downstream will accept, for instance), the valve shuts
the P->A path and diverts the excess to T instead of leaving the
outlet floating above p_set. The user wires T to a Reservoir node, same
as any other tank port in this codebase.

Scope note: `Q_A` stays <= 0 (forward/outgoing) even when relieving --
this valve handles "supply forces more flow than the downstream will
accept", not "something external actively pushes flow backward into
A". Conservation alone routes the excess to T once Q_P is forced by an
upstream flow source; A never needs to reverse for that. True external
backfeed into A is deferred (see spec Non-goals) -- an earlier version
made A bidirectional for that case, but it was unnecessary for every
realistic circuit tried and only widened the space of competing roots.

Equations, when relieving=True: a dual Fischer-Burmeister pairing
sharing the same cap term `a = (p_set - P_A)/P_scale`, one for the
supply path (P vs A) and one for the relief path (T vs A) -- see
`equations()` for the exact residuals and why each correction term
(reverse-flow penalty, supply ridge, relief ridge) exists. This
replaced an earlier hard-branch design (`if P_a > p_set and Q_p <= 0`)
that pinned Q_p to exactly zero -- that directly contradicted any
upstream flow SOURCE that forces its own nonzero Q_p (e.g. a
fixed-displacement pump), corrupting the shared pressure instead of
converging. See `docs/superpowers/specs/2026-09-03-pressure-reducing-valve-relief-port-design.md`
for the full derivation, the numerical spike that validated this
formulation, and the known trade-off in the supply ridge (Important:
read that spec's "Remaining known limitation" before touching the
tuning constants below).
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
        # Q_A stays <= 0 (forward/outgoing only) even when relieving --
        # scoped out: this valve handles "supply forces more flow than the
        # downstream will accept" (diverted to T without ever reversing
        # A), not "something external actively pushes flow backward into
        # A". Conservation alone routes the excess to T once Q_P is
        # forced by an upstream flow source, with no need for A to
        # reverse. See spec Non-goals for the deferred backfeed case.
        b = {
            self.flow_var_p: (0.0, None),    # Q_P never negative -- forward flow only
            self.flow_var_a: (None, 0.0),    # Q_A never positive -- forward/outgoing only
        }
        if self.relieving:
            b[self.flow_var_t] = (None, 0.0)   # Q_T never positive -- only leaves via T
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

        if not self.relieving:
            # Unchanged from the shipped 2-port valve, closed-regime
            # branch included: if the outlet is already above p_set with
            # no forward flow trying to happen, the FB pairing below has
            # no root (a = p_set - P_a stays negative regardless of b),
            # so pin Q_p to zero directly instead of forcing an
            # infeasible pairing.
            eq_conservation = (Q_p + Q_a) / Q_scale
            if P_a > self.p_set and Q_p <= 0:
                eq_supply = Q_p / Q_scale
            else:
                a = (self.p_set - P_a) / P_scale
                b = (P_p - P_a) / P_scale
                eq_supply = a + b - math.sqrt(a * a + b * b)
            return [eq_conservation, eq_supply]

        # relieving=True: dual Fischer-Burmeister pairing sharing the same
        # cap term `a`, instead of the branch-guard version above. Neither
        # equation pins Q_p or Q_a to a specific value -- only P_A's cap is
        # enforced; the actual split of flow between P and T emerges from
        # conservation plus whatever is externally connected to each port
        # (e.g. a fixed-displacement pump forces Q_p regardless of what
        # this valve "wants"; the branch-guard version's hard Q_p=0 pin
        # directly contradicted that and blew up the shared pressure).
        Q_t = x[idx[self.flow_var_t]]
        eq_conservation = (Q_p + Q_a + Q_t) / Q_scale

        a = (self.p_set - P_a) / P_scale  # shared cap term

        b_supply = (P_p - P_a) / P_scale
        eq_supply = a + b_supply - math.sqrt(a * a + b_supply * b_supply)
        # P_p is mathematically underdetermined once regulating (this
        # equation only demands P_p >= p_set, an inequality) -- if nothing
        # upstream pins it (e.g. a fixed-displacement pump, which forces
        # only Q_p, never P_p), the solver has a free direction to drift
        # in and struggles to converge. Fix: a ridge pulling P_p toward
        # p_set (the minimal valid value) unless something else in the
        # network genuinely pins it higher.
        #
        # Deliberately a function of P_p vs. the FIXED constant p_set,
        # NOT of (P_p - P_a): an earlier version used b_supply directly,
        # which let the solver "cheat" by raising P_a instead of lowering
        # P_p whenever P_p was hard-pinned high by something upstream
        # (e.g. a fixed-pressure reservoir) -- it dragged the capped
        # outlet UP to match, defeating the valve's entire purpose. Since
        # this term never mentions P_a, there is no such escape route.
        # Saturating (tanh), not linear: a linear ridge adds a residual
        # proportional to (P_p - p_set), which never reaches zero when
        # P_p is legitimately pinned far above p_set -- the solver then
        # has to deviate P_a from the exact root (a=0) just to cancel
        # that leftover constant. tanh caps the distortion at
        # +-SUPPLY_RIDGE_WEIGHT regardless of how large the gap is, and
        # vanishes exactly at P_p=p_set (the free/underdetermined case),
        # so the exact root is reachable there with zero compromise.
        # One-sided: smooth_max0 zeroes this out whenever P_p <= p_set, so
        # the fully-open regime (P_p naturally below p_set, a legitimate,
        # already well-determined state) is never disturbed -- only the
        # genuinely underdetermined "P_p pinned above p_set" direction is
        # discouraged. An earlier version used a plain tanh(...) without
        # this gate and measurably distorted the fully-open regime too.
        SUPPLY_RIDGE_WEIGHT = 2.0
        gap = (P_p - self.p_set) / P_scale
        gap_above = (gap + math.sqrt(gap * gap + 1e-18)) / 2.0
        eq_supply += SUPPLY_RIDGE_WEIGHT * math.tanh(gap_above)
        # Reverse-flow exclusion at the equation level (not just via
        # `bounds`, which fsolve's own unbounded stage ignores entirely).
        PENALTY_WEIGHT = 500.0
        z = -Q_p / Q_scale
        eq_supply += ((z + math.sqrt(z * z + 1e-18)) / 2.0) * PENALTY_WEIGHT

        b_relief = -Q_t / Q_scale
        eq_relief = a + b_relief - math.sqrt(a * a + b_relief * b_relief)
        # Tie-break for the rank-deficient shared root (a=0): pulls Q_t
        # toward 0 unless relief is genuinely needed to hold the cap.
        RIDGE_WEIGHT = 0.0002
        eq_relief += RIDGE_WEIGHT * (Q_t / Q_scale)

        return [eq_conservation, eq_supply, eq_relief]

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
