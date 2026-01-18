# domain/connections.py

from __future__ import annotations
from typing import Tuple
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
        """Dado um anchor da conexão, retorna o outro."""
        if anchor == self.anchor_a:
            return self.anchor_b
        elif anchor == self.anchor_b:
            return self.anchor_a
        else:
            raise ValueError(f"Anchor {anchor.id} not in connection {self.id}")