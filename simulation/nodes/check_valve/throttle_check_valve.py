"""Simulation node for the throttle check valve.

Behaviour
---------
The valve connects anchors X (left) and Y (right).

Free flow direction  (check valve open — instant):
    Y=1, X=0  →  X becomes 1 immediately.

Restricted direction (throttle path — delayed):
    X=1, Y=0  →  Y becomes 1 after `delay_steps` simulation steps.

Same state on both sides  →  no transfer, any pending counter is aborted.

The number of delay steps is read from ``properties["delay_steps"]``
(default: 3).  The sprite state exposed via ``get_visual_state()`` is
``"open"`` while a transfer is in progress, ``"closed"`` otherwise.
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

        # Counter: >0 means a delayed transfer is in progress.
        # -1 means idle / no pending transfer.
        self._steps_remaining: int = -1

        # Track whether a transfer is happening for visual state.
        self._transferring: bool = False

    # ------------------------------------------------------------------
    # Simulation contract
    # ------------------------------------------------------------------

    def update(self, outputs=None):
        """Decide connectivity each iteration."""
        x = self.anchors["X"].state
        y = self.anchors["Y"].state

        if x == y:
            # Both same — abort any pending delayed transfer, hold state.
            self._steps_remaining = -1
            self._transferring = False
            return

        if y and not x:
            # Free-flow direction: Y→X, pass through instantly.
            self.anchors["X"].state = True
            self._steps_remaining = -1
            self._transferring = True
            return

        if x and not y:
            # Restricted direction: X→Y, needs delay.
            if self._steps_remaining < 0:
                # Start counting.
                self._steps_remaining = self._delay_steps
            self._transferring = True
            # Actual transfer happens in post_step_update.

    def post_step_update(self, dt=None):
        """Tick the delay counter; perform restricted transfer when done."""
        super().post_step_update(dt=dt)

        if self._steps_remaining <= 0:
            return

        self._steps_remaining -= 1

        if self._steps_remaining == 0:
            self.anchors["Y"].state = True
            self._steps_remaining = -1

    def get_internal_connections(self):
        """Return a direct X↔Y connection when in free-flow state."""
        x = self.anchors["X"].state
        y = self.anchors["Y"].state
        if y and not x:
            return [("X", "Y")]
        return []

    # ------------------------------------------------------------------
    # Visual state
    # ------------------------------------------------------------------

    def get_visual_state(self) -> str:
        """``"open"`` while transferring in either direction, else ``"closed"``."""
        return "open" if self._transferring else "closed"

    # ------------------------------------------------------------------
    # Undo / history
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        state = super().get_state()
        state["steps_remaining"] = self._steps_remaining
        state["transferring"] = self._transferring
        return state

    def set_state(self, state: dict):
        super().set_state(state)
        self._steps_remaining = state.get("steps_remaining", -1)
        self._transferring = state.get("transferring", False)
        # Sync delay_steps in case properties changed between snapshots.
        self._delay_steps = int(
            (self.properties or {}).get("delay_steps", _DEFAULT_DELAY)
        )
