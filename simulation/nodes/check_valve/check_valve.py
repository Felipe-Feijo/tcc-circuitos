"""Simulation node for the check valve (pneumatic only).

Behaviour
---------
The valve exposes two anchors X (left) and Y (right), and optionally a
third anchor Z (pilot), present only when properties["piloted"] is True.

Free-flow (Y=1, independente de X): conecta X<->Y.
Blocked (Y=0, independente de X): nunca conecta.

Pilotagem (Z=1, só quando properties["piloted"] é True): força X<->Y
sempre conectado, independente do estado de Y.

Tudo instantâneo -- sem contador/delay, diferente da throttle_check_valve
(prima na mesma pasta check_valve/).

Visual state (ver get_visual_state):
    "open"   -- Y=1 (com ou sem força de piloto)
    "closed" -- Y=0 e (não piloted ou Z=0)
"""

from __future__ import annotations
from simulation.nodes.nodes import Node


class CheckValve(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "check_valve", domain=domain, properties=properties)

        self._open: bool = False
        self._sprite: str = "closed"

    def update(self, outputs=None):
        pass  # decisão só em post_step_update, como a throttle_check_valve

    def post_step_update(self, dt=None):
        super().post_step_update(dt=dt)

        y = self.anchors["Y"].state
        piloted = (self.properties or {}).get("piloted", False)
        z_forced = piloted and self.anchors["Z"].state

        self._open = bool(z_forced or y)
        self._sprite = "open" if self._open else "closed"

    def get_internal_connections(self):
        if self._open:
            return [("X", "Y")]
        return []

    def get_visual_state(self) -> str:
        return self._sprite

    def get_state(self) -> dict:
        state = super().get_state()
        state["open"] = self._open
        state["sprite"] = self._sprite
        return state

    def set_state(self, state: dict):
        super().set_state(state)
        self._open = state.get("open", False)
        self._sprite = state.get("sprite", "closed")
