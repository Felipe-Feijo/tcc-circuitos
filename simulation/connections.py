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
        
    def get_state(self) -> float:
        domain = getattr(self.anchor_a, "domain", "pneumatic")
        
        if domain in ["pneumatic", "electric"]:
            return 1 if self.anchor_a.state and self.anchor_b.state else 0
        elif domain == "hydraulic":
            if not self.anchor_a.fault and not self.anchor_b.fault:
                avg = (self.anchor_a.pressure + self.anchor_b.pressure) / 2
                return 0.0 if abs(avg) < 1e-10 else avg
            else:
                return None  # falha na conexão, sem fluxo
        else:
            return 0