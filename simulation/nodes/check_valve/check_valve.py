"""Simulation node for the check valve (pneumatic and hydraulic).

Behaviour (pneumatic)
----------------------
The valve exposes two anchors X (left) and Y (right), and optionally a
third anchor Z (pilot), present only when properties["piloted"] is True.

Two very different mechanisms are at play, depending on whether the
pilot is currently forcing the valve open:

1. Normal check function (Z not forcing, decided purely by Y):
   X does NOT get merged with Y via get_internal_connections() -- see
   below for why. Instead X acts as its own pressure driver
   (anchor.is_driver = True, exactly like PressureSource/Exhaust do for
   their own anchors in simulation/nodes/nodes.py) ONLY WHILE Y=1, and
   is only ever pushed to state=True, never back to False by this node.
   The moment Y drops, X.is_driver goes back to False -- X becomes an
   ordinary follower again. This matters: if X stayed a driver forever,
   SimulationEngine's group algorithm would never update X's OWN state
   again (drivers are never overwritten by _update_pneumatic_domain), so
   X would keep reporting a stale True even after a real exhaust
   downstream vented the rest of its group to False. As a plain
   follower, X correctly freezes (no driver anywhere in its group --
   trapped pressure held) or correctly follows a real driver (exhaust or
   new source) that's actually there.

   A symmetric union of X and Y (the mechanism get_internal_connections()
   normally triggers via SimulationEngine._get_connected_group()) has no
   direction: once merged, ANY driver reachable from either side
   (including an exhaust that later reaches Y when an upstream
   directional valve switches from supply to exhaust) forces the WHOLE
   merged group down, leaking pressure backwards through what should be
   a closed valve. A real check valve must never do that in this mode --
   once pressure passes through, it stays trapped on the X side even
   after Y is vented, until something downstream of X actively vents it.

   This is also why there's no one-step propagation lag here (unlike the
   old get_internal_connections-based design this replaced): update()
   runs every fixed-point iteration (before the domain is resolved for
   that iteration), so X latches to True within the same simulation step
   Y turns 1 in.

2. Pilot-forced-open (properties["piloted"] is True and Z=1): the pilot
   mechanically holds the poppet away from its seat -- the valve becomes
   a plain, direction-less open passage, exactly like an ordinary open
   valve or a piece of pipe. This is the intentional use case for a
   pilot-operated check valve: releasing pressure that would otherwise be
   trapped (e.g. unlocking a load-holding cylinder). So while forced
   open, X stops being an artificial driver (is_driver = False) and
   get_internal_connections() DOES return [("X", "Y")] -- the ordinary
   symmetric union takes over, and whatever real drivers exist on either
   side (a source, an exhaust, or none) decide the merged group's state
   exactly like any other passive two-port component.

Free-flow (Y=1, regardless of X, with no pilot forcing): latches X to
True (mode 1).
Blocked (Y=0, with no pilot forcing): does nothing -- X keeps whatever
it already had (trapped pressure, doesn't retreat).
Piloting (Z=1, only when properties["piloted"] is True): unites X and Y
symmetrically (mode 2) -- stops being a diode, becomes an open passage.

Behaviour (hydraulic)
-----------------------
Simpler than pneumatic: no state of its own, everything decided each
solve by the equations. Models the valve via smoothed complementarity
(Fischer-Burmeister), the same mechanism ReliefValve
(simulation/nodes/relief_valve.py) already uses to switch between two
regimes without an abrupt transition that would break the solver's
convergence:

    a = Q_Y / Q_scale                (wants a >= 0)
    b = (P_X - P_Y) / P_scale        (wants b >= 0)
    eq_fb = a + b - sqrt(a^2 + b^2)    (== 0  =>  a>=0, b>=0, a*b=0)

`b = P_X - P_Y` is the "sealing backpressure": when X (downstream) is
more pressurized than Y (upstream), b>=0 and the ball is pushed against
the seat -- blocked (a=0, Q_Y=0), but P_X can exceed P_Y freely
(sealed). When Y can push the ball (favorable flow), b=0 (no pressure
drop, P_X=P_Y) and a=Q_Y>=0 is free.

In other words: EITHER the valve is closed (Q_Y = 0, with P_X free to
sit above P_Y -- sealed), OR it's open with zero pressure drop (P_Y =
P_X, Q_Y >= 0 free) -- never both at once. Plus flow conservation (no
internal accumulation):

    Q_X + Q_Y = 0

Piloting (properties["piloted"] is True and the pressure at Z >= 1 bar):
replaces the complementarity with an unconditional zero-pressure-drop
equation (P_X = P_Y) -- the pilot mechanically pushes the ball off its
seat, and the valve becomes an open passage in both directions, with no
direction restriction at all. Below 1 bar at the pilot, behaves exactly
like the non-piloted version.

The Z anchor, when present, is modeled as a "dead" port: flow always
zero (Q_Z = 0, a pressure sensor, not a real flow port) -- it only
needs its own equation to close the system (give the solver an
equation for the Q_Z variable that only this valve uses); the pressure
at Z stays free, determined by the rest of the circuit wired to it.

Unlike hydraulic directional valves (Valve_3_2_Ways), there's no
required property like "k" -- the check valve models no
resistance/orifice, only the direction restriction.

Visual state (see get_visual_state):
    "open"   -- Y=1/Q_Y>0 or the pilot forcing it open
    "closed" -- otherwise
"""

from __future__ import annotations

import math

from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin

_PILOT_PRESSURE_THRESHOLD = 1e5  # 1 bar, in Pa


class CheckValve(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "check_valve", domain=domain, properties=properties)

        if self.domain == "hydraulic":
            self._piloted_hydraulic = bool((self.properties or {}).get("piloted", False))
            self.flow_var_x = f"Q_{self.id}_X"
            self.flow_var_y = f"Q_{self.id}_Y"
            if self._piloted_hydraulic:
                self.flow_var_z = f"Q_{self.id}_Z"

    # ------------------------------------------------------------------
    # Pneumatic domain
    # ------------------------------------------------------------------

    def _piloted_open(self) -> bool:
        piloted = (self.properties or {}).get("piloted", False)
        return bool(piloted and "Z" in self.anchors and self.anchors["Z"].state)

    def update(self, outputs=None):
        if self.domain != "pneumatic":
            return

        x_anchor = self.anchors["X"]

        if self._piloted_open():
            # Symmetric open passage -- get_internal_connections() is
            # what unites X and Y now; X shouldn't pretend to be a
            # driver here, or it contaminates the group with an
            # artificial value instead of letting the real drivers (on
            # either side) decide.
            x_anchor.is_driver = False
            return

        if self.anchors["Y"].state:
            x_anchor.is_driver = True
            x_anchor.state = True
        else:
            x_anchor.is_driver = False

    def get_internal_connections(self):
        if self._piloted_open():
            return [("X", "Y")]
        return []

    def get_visual_state(self) -> str:
        if self.domain == "hydraulic":
            y_flow = self.anchors["Y"].flow
            flowing = isinstance(y_flow, (int, float)) and y_flow > 0
            return "open" if (flowing or self._piloted_open_hydraulic()) else "closed"

        y = self.anchors["Y"].state
        return "open" if (y or self._piloted_open()) else "closed"

    # ------------------------------------------------------------------
    # Hydraulic domain
    # ------------------------------------------------------------------

    def _piloted_open_hydraulic(self) -> bool:
        if not self._piloted_hydraulic:
            return False
        p_z = self.anchors["Z"].pressure
        return isinstance(p_z, (int, float)) and p_z >= _PILOT_PRESSURE_THRESHOLD

    @property
    def variables(self):
        if self.domain != "hydraulic":
            return []
        vars_ = [self.flow_var_x, self.flow_var_y]
        if self._piloted_hydraulic:
            vars_.append(self.flow_var_z)
        for anchor_name in self.hydraulic_ports().keys():
            anchor = self.anchors.get(anchor_name)
            if anchor and anchor.pressure_var:
                vars_.append(anchor.pressure_var)
        return vars_

    def hydraulic_ports(self):
        if self.domain != "hydraulic":
            return {}
        ports = {"X": self.flow_var_x, "Y": self.flow_var_y}
        if self._piloted_hydraulic:
            ports["Z"] = self.flow_var_z
        return ports

    @property
    def bounds(self):
        if self.domain != "hydraulic" or self._piloted_hydraulic:
            # Piloted: can operate in either check mode OR free passage
            # (both directions) depending on the pilot pressure,
            # evaluated inside equations() -- locking Q_Y/Q_X to one
            # direction would break the free mode. No bounds here, the
            # equation itself decides.
            return {}
        return {
            self.flow_var_y: (0.0, None),   # Q_Y never negative
            self.flow_var_x: (None, 0.0),   # Q_X never positive
        }

    @property
    def initial_guess(self):
        if self.domain != "hydraulic":
            return {}
        guess = {
            self.flow_var_x: -1.0,
            self.flow_var_y: 1.0,
        }
        if self._piloted_hydraulic:
            guess[self.flow_var_z] = 0.0
        return guess

    def equations(self, x, idx):
        Q_x = x[idx[self.flow_var_x]]
        Q_y = x[idx[self.flow_var_y]]
        P_x = x[idx[self.anchors["X"].pressure_var]]
        P_y = x[idx[self.anchors["Y"].pressure_var]]

        Q_scale = max(self.q_ref, 1e-12)
        P_scale = max(self.p_ref, 1e-3)

        eq_conservation = (Q_x + Q_y) / Q_scale

        piloted_open = False
        eqs_extra = []
        if self._piloted_hydraulic:
            Q_z = x[idx[self.flow_var_z]]
            eqs_extra.append(Q_z / Q_scale)  # dead port -- sensing only

            P_z = x[idx[self.anchors["Z"].pressure_var]]
            piloted_open = P_z >= _PILOT_PRESSURE_THRESHOLD

        if piloted_open:
            eq_dp = (P_x - P_y) / P_scale
            return [eq_conservation, eq_dp] + eqs_extra

        a = Q_y / Q_scale
        b = (P_x - P_y) / P_scale
        eq_fb = a + b - math.sqrt(a * a + b * b)
        return [eq_conservation, eq_fb] + eqs_extra
