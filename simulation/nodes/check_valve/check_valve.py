"""Simulation node for the check valve (pneumatic only).

Behaviour
---------
The valve exposes two anchors X (left) and Y (right), and optionally a
third anchor Z (pilot), present only when properties["piloted"] is True.

Unlike most two-port components, this valve does NOT declare an internal
connection between X and Y (get_internal_connections() is always empty).
A symmetric union of X and Y -- the mechanism get_internal_connections()
normally triggers via SimulationEngine._get_connected_group() -- has no
direction: once merged, ANY driver reachable from either side (including
an exhaust that later reaches Y when an upstream directional valve
switches from supply to exhaust) forces the WHOLE merged group down,
leaking pressure backwards through what should be a closed valve. A real
check valve must never do that: once pressure passes through, it stays
trapped on the X side even after Y is vented, until something downstream
of X actively vents it.

Instead, X acts as its own pressure driver (anchor.is_driver = True --
exactly like PressureSource/Exhaust do for their own anchors in
simulation/nodes/nodes.py) and this node only ever pushes X to
state=True; it never pushes X back to False itself. Downstream circuits
can still vent X normally: SimulationEngine computes
group_state = all(driver.state for driver in group), so a real exhaust
anywhere in X's own connected group still forces that group (and X) to
False -- this component just never does that job itself.

This also removes the one-step propagation lag the previous
get_internal_connections-based design had: update() runs every
fixed-point iteration (before the domain is resolved for that
iteration), so X latches to True within the same simulation step Y
turns 1 in, not one step later.

Free-flow (Y=1, independente de X): latches X to True.
Blocked (Y=0, independente de X): não faz nada -- X mantém o que já tinha
(pressão retida, não recua).

Pilotagem (Z=1, só quando properties["piloted"] é True): também latches X
to True, independente de Y.

Visual state (ver get_visual_state) reflete se há fluxo novo passando
agora (Y=1 ou piloto ativo) -- não o valor latched de X. Fisicamente a
válvula fecha (mola) assim que Y cai, mesmo que X continue pressurizado
(pressão retida a jusante):
    "open"   -- Y=1 ou (piloted e Z=1)
    "closed" -- caso contrário
"""

from __future__ import annotations
from simulation.nodes.nodes import Node


class CheckValve(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "check_valve", domain=domain, properties=properties)

    def _is_conducting(self) -> bool:
        y = self.anchors["Y"].state
        piloted = (self.properties or {}).get("piloted", False)
        z_forced = piloted and "Z" in self.anchors and self.anchors["Z"].state
        return bool(y or z_forced)

    def update(self, outputs=None):
        x_anchor = self.anchors["X"]
        x_anchor.is_driver = True
        if self._is_conducting():
            x_anchor.state = True
        # else: leave X.state untouched -- latched/trapped pressure.

    def get_internal_connections(self):
        # Deliberately always empty -- see module docstring.
        return []

    def get_visual_state(self) -> str:
        return "open" if self._is_conducting() else "closed"
