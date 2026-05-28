"""Simulation node for the throttle check valve.

Behaviour
---------
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
"""

from __future__ import annotations
from simulation.nodes.nodes import Node

_DEFAULT_DELAY = 3


class ThrottleCheckValve(Node):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(
            node_id, "throttle_check_valve", domain=domain, properties=properties
        )

        self._delay_steps: int = int(
            (self.properties or {}).get("delay_steps", _DEFAULT_DELAY)
        )

        # 0 = idle. >0 = counting down.
        self._steps_remaining: int = 0

        # Whether the valve is open (X ↔ Y connected).
        self._open: bool = False

        # Latched sprite — only updated in post_step_update on stabilised states.
        self._sprite: str = "open"

    # ------------------------------------------------------------------
    # Simulation contract
    # ------------------------------------------------------------------

    def update(self, outputs=None):
        """Expose _open to the engine — no decisions made here."""
        pass

    def post_step_update(self, dt=None):
        """All logic runs here on fully stabilised anchor states."""
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
        if self._open:
            return [("X", "Y")]
        return []

    # ------------------------------------------------------------------
    # Visual state
    # ------------------------------------------------------------------

    def get_visual_state(self) -> str:
        return self._sprite

    # ------------------------------------------------------------------
    # Undo / history
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        state = super().get_state()
        state["steps_remaining"] = self._steps_remaining
        state["open"] = self._open
        state["sprite"] = self._sprite
        return state

    def set_state(self, state: dict):
        super().set_state(state)
        self._steps_remaining = state.get("steps_remaining", 0)
        self._open = state.get("open", False)
        self._sprite = state.get("sprite", "open")
        self._delay_steps = int(
            (self.properties or {}).get("delay_steps", _DEFAULT_DELAY)
        )