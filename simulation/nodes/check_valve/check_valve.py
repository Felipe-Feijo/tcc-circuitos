"""Simulation node for the check valve (pneumatic only).

Behaviour
---------
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

Free-flow (Y=1, independente de X, sem pilotagem forçando): latches X to
True (modo 1).
Blocked (Y=0, sem pilotagem forçando): não faz nada -- X mantém o que já
tinha (pressão retida, não recua).
Pilotagem (Z=1, só quando properties["piloted"] é True): une X e Y
simetricamente (modo 2) -- deixa de ser um diodo, vira passagem aberta.

Visual state (ver get_visual_state):
    "open"   -- Y=1 ou (piloted e Z=1)
    "closed" -- caso contrário
"""

from __future__ import annotations
from simulation.nodes.nodes import Node


class CheckValve(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "check_valve", domain=domain, properties=properties)

    def _piloted_open(self) -> bool:
        piloted = (self.properties or {}).get("piloted", False)
        return bool(piloted and "Z" in self.anchors and self.anchors["Z"].state)

    def update(self, outputs=None):
        x_anchor = self.anchors["X"]

        if self._piloted_open():
            # Passagem aberta simétrica -- get_internal_connections() é
            # quem une X e Y agora; X não deve fingir ser driver aqui,
            # senão contamina o grupo com um valor artificial em vez de
            # deixar os drivers reais (dos dois lados) decidirem.
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
        y = self.anchors["Y"].state
        return "open" if (y or self._piloted_open()) else "closed"
