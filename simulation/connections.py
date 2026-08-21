"""Represents connections between anchors in the simulation domain.

A Connection is non-directional: it connects two Anchor objects and
notifies both at creation time. Used by SimulationEngine to propagate
state between pneumatic, electric and hydraulic domain nodes.
"""

from __future__ import annotations

from simulation.nodes.nodes import Anchor


class Connection:
    def __init__(self, anchor_a: Anchor, anchor_b: Anchor):
        self.anchor_a = anchor_a
        self.anchor_b = anchor_b

        self.id = frozenset([anchor_a.id, anchor_b.id])

        anchor_a.connect(self)
        anchor_b.connect(self)

    def anchors(self) -> tuple[Anchor, Anchor]:
        return self.anchor_a, self.anchor_b

    def get_other(self, anchor: Anchor) -> Anchor:
        """Returns the anchor opposite the one given.

        Args:
            anchor: One of the connection's two anchors.

        Returns:
            The anchor at the other end of the connection.

        Raises:
            ValueError: If the given anchor doesn't belong to this connection.
        """
        if anchor == self.anchor_a:
            return self.anchor_b
        elif anchor == self.anchor_b:
            return self.anchor_a
        else:
            raise ValueError(f"Anchor {anchor.id} not in connection {self.id}")

    def get_state(self) -> float:
        """Returns the connection's state according to the domain.

        For pneumatic and electric domains, returns 1 if both anchors are
        active, 0 otherwise. For the hydraulic domain, returns the average
        pressure or an error/pressurizing status string.

        Returns:
            0 or 1 for pneumatic/electric; average pressure (float),
            "ERR" or "PRESSURIZING" for hydraulic.
        """
        domain = getattr(self.anchor_a, "domain", "pneumatic")

        if domain in ["pneumatic", "electric"]:
            return 1 if self.anchor_a.state and self.anchor_b.state else 0
        elif domain == "hydraulic":
            p_a = self.anchor_a.pressure
            p_b = self.anchor_b.pressure
            if isinstance(p_a, str) or isinstance(p_b, str):
                return "ERR"
            if self.anchor_a.pressurizing or self.anchor_b.pressurizing:
                return "PRESSURIZING"
            avg = (p_a + p_b) / 2
            return 0.0 if abs(avg) < 1e-10 else avg
