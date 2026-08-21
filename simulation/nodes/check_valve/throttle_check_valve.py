"""Simulation node for the throttle check valve (pneumatic and hydraulic).

Behaviour (pneumatic)
----------------------
The valve exposes two anchors X (left) and Y (right).  State propagation
is handled entirely by the engine through get_internal_connections().

Free-flow direction (Y=1, X=0):
    Connects X↔Y immediately.

Restricted direction (X=1, Y=0):
    Connects X↔Y after `delay_steps` simulation steps.

Same state (X=Y):
    Disconnects X↔Y, holds last sprite state.

All decisions — connection, counter, and sprite latch — are made in
post_step_update(), which sees the fully stabilised anchor states.
update() only exposes the current _open flag to get_internal_connections().

Visual state (latched in post_step_update):
    "open"   — last stabilised direction was free-flow  (Y=1, X=0)
    "closed" — last stabilised direction was restricted  (X=1, Y=0)
    Default: "open"

`delay_steps` is read from ``properties["delay_steps"]`` (default: 3).
`delay_steps` is only used in the pneumatic domain.

Behaviour (hydraulic)
-----------------------
A real "one-way flow control valve": a free check path in parallel with
a fixed orifice -- unlike a pure check valve
(simulation/nodes/check_valve/check_valve.py), the restricted direction
NEVER blocks, it only resists. That's why the pneumatic side uses a
delay (`delay_steps`) instead of blocking: the delay approximates, in
the boolean domain, the time a resisted flow would take to pressurize
the downstream side -- the hydraulic side needs no delay at all, the
orifice equation already gives the continuous dP-Q relation directly.

    b = P_X - P_Y

    Q_Y >= 0  (Y pushes, favorable direction):
        zero resistance -- P_X = P_Y, same as the pure check valve's
        open branch (check_valve.py).

    Q_Y < 0  (restricted direction):
        does NOT block -- passes through the fixed orifice (conductance `k`):
        b = copysign((Q_Y / k)^2, -Q_Y)
        (same turbulent-orifice equation Valve_3_2_Ways uses; tying the
        sign to -Q_Y guarantees the flow is negative in Y -- exiting
        through Y, entering through X -- on this branch).

The branch uses Q_Y's sign -- not P_X-P_Y's -- on purpose: P_X/P_Y are
this solve's own unknowns, so branching on them is circular. The
favorable branch mentions Q_Y in no equation, so if the branch were
chosen by pressure, P_X=P_Y=0 would satisfy the "favorable" branch even
with a Q_Y clearly in the restricted direction (imposed externally, by
a fixed-flow pump for example) -- a spurious root where the pressure
never rises to overcome the orifice. Q_Y is already determined by
conservation + whatever is connected to the valve, so branching on it
eliminates that ambiguity.

Unlike the pure check valve, this is NOT complementarity (never forces
flow or pressure exactly to zero) -- it's a resistance that changes
value depending on direction, so it uses a hard branch (if/else, same
as ReliefValve already uses) instead of Fischer-Burmeister.

`k` is required in the hydraulic domain (same pattern as Valve_3_2_Ways).
Plus flow conservation: Q_X + Q_Y = 0.

Visual state (see get_visual_state):
    "open"   -- b <= 0 (favorable direction, no resistance)
    "closed" -- b > 0 (restricted direction, passing through the orifice)
"""

from __future__ import annotations

import math

from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin

_DEFAULT_DELAY = 3


class ThrottleCheckValve(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(
            node_id, "throttle_check_valve", domain=domain, properties=properties
        )

        if self.domain == "hydraulic":
            k = self.properties.get("k")
            if k is None:
                raise ValueError(
                    f"ThrottleCheckValve '{self.id}': required property 'k' is not set."
                )
            self.k = float(k)
            self.flow_var_x = f"Q_{self.id}_X"
            self.flow_var_y = f"Q_{self.id}_Y"
        else:
            self._delay_steps: int = int(
                (self.properties or {}).get("delay_steps", _DEFAULT_DELAY)
            )

            # 0 = idle. >0 = counting down.
            self._steps_remaining: int = 0

            # Whether the valve is open (X ↔ Y connected).
            self._open: bool = False

            # Latched sprite -- only updated in post_step_update on stabilised states.
            self._sprite: str = "open"

    # ------------------------------------------------------------------
    # Pneumatic domain
    # ------------------------------------------------------------------

    def update(self, outputs=None):
        """Expose _open to the engine — no decisions made here."""
        pass

    def post_step_update(self, dt=None):
        """All logic runs here on fully stabilised anchor states."""
        if self.domain != "pneumatic":
            return
        super().post_step_update(dt=dt)

        x = self.anchors["X"].state
        y = self.anchors["Y"].state

        if x == y:
            # Same state — disconnect, hold sprite.
            self._open = False
            self._steps_remaining = 0
            return

        if y and not x:
            # Free-flow — connect immediately, latch sprite open.
            self._open = True
            self._sprite = "open"
            self._steps_remaining = 0
            return

        # x and not y — restricted direction.
        self._sprite = "closed"

        if self._open:
            # Already open from a previous step — stay open.
            return

        if self._steps_remaining == 0:
            self._steps_remaining = self._delay_steps

        self._steps_remaining -= 1

        if self._steps_remaining <= 0:
            self._steps_remaining = 0
            self._open = True

    def get_internal_connections(self):
        if self.domain != "pneumatic":
            return []
        if self._open:
            return [("X", "Y")]
        return []

    def get_visual_state(self) -> str:
        if self.domain == "hydraulic":
            p_x = self.anchors["X"].pressure
            p_y = self.anchors["Y"].pressure
            if isinstance(p_x, (int, float)) and isinstance(p_y, (int, float)):
                return "closed" if (p_x - p_y) > 0 else "open"
            return "open"
        return self._sprite

    # ------------------------------------------------------------------
    # Undo / history (pneumatic only -- hydraulic has no state of its
    # own, everything decided each solve by the equations)
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        state = super().get_state()
        if self.domain == "pneumatic":
            state["steps_remaining"] = self._steps_remaining
            state["open"] = self._open
            state["sprite"] = self._sprite
        return state

    def set_state(self, state: dict):
        super().set_state(state)
        if self.domain != "pneumatic":
            return
        self._steps_remaining = state.get("steps_remaining", 0)
        self._open = state.get("open", False)
        self._sprite = state.get("sprite", "open")
        self._delay_steps = int(
            (self.properties or {}).get("delay_steps", _DEFAULT_DELAY)
        )

    # ------------------------------------------------------------------
    # Hydraulic domain
    # ------------------------------------------------------------------

    @property
    def variables(self):
        if self.domain != "hydraulic":
            return []
        vars_ = [self.flow_var_x, self.flow_var_y]
        for anchor_name in self.hydraulic_ports().keys():
            anchor = self.anchors.get(anchor_name)
            if anchor and anchor.pressure_var:
                vars_.append(anchor.pressure_var)
        return vars_

    def hydraulic_ports(self):
        if self.domain != "hydraulic":
            return {}
        return {"X": self.flow_var_x, "Y": self.flow_var_y}

    @property
    def initial_guess(self):
        if self.domain != "hydraulic":
            return {}
        return {self.flow_var_x: -1.0, self.flow_var_y: 1.0}

    def equations(self, x, idx):
        Q_x = x[idx[self.flow_var_x]]
        Q_y = x[idx[self.flow_var_y]]
        P_x = x[idx[self.anchors["X"].pressure_var]]
        P_y = x[idx[self.anchors["Y"].pressure_var]]

        Q_scale = max(self.q_ref, 1e-12)
        P_scale = max(self.p_ref, 1e-3)

        eq_conservation = (Q_x + Q_y) / Q_scale

        # The branch uses Q_y's sign -- imposed externally by the rest of
        # the circuit (e.g. a fixed-flow pump) -- not P_X - P_Y's.
        # Branching by pressure would be circular: P_X/P_Y are this
        # solve's own unknowns, so the "favorable" branch (which
        # mentions no Q_y) could be satisfied by P_X=P_Y=0 even when Q_y
        # is clearly in the restricted direction (forced externally),
        # since nothing in that branch validates the flow's real
        # direction -- a spurious root. Branching by Q_y (already
        # determined by conservation + whatever is connected to the
        # valve) eliminates that ambiguity.
        b = P_x - P_y
        if Q_y >= 0:
            # Favorable direction -- zero resistance, same branch as the
            # pure check valve when open.
            eq_valve = (P_x - P_y) / P_scale
        else:
            # Restricted direction -- doesn't block, passes through the fixed orifice.
            eq_valve = (b - math.copysign((Q_y / self.k) ** 2, -Q_y)) / P_scale

        return [eq_conservation, eq_valve]
