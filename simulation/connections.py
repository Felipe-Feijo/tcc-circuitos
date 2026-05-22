"""Representa conexões entre âncoras no domínio de simulação.

Uma Connection é não-direcional: conecta dois objetos Anchor e notifica
ambos no momento da criação. Usada pelo SimulationEngine para propagar
estado entre nós de domínios pneumático, elétrico e hidráulico.
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
        """Retorna o âncora oposto ao fornecido.

        Args:
            anchor: Um dos dois âncoras da conexão.

        Returns:
            O âncora na outra extremidade da conexão.

        Raises:
            ValueError: Se o âncora fornecido não pertencer a esta conexão.
        """
        if anchor == self.anchor_a:
            return self.anchor_b
        elif anchor == self.anchor_b:
            return self.anchor_a
        else:
            raise ValueError(f"Anchor {anchor.id} not in connection {self.id}")

    def get_state(self) -> float:
        """Retorna o estado da conexão de acordo com o domínio.

        Para domínios pneumático e elétrico, retorna 1 se ambos os âncoras
        estiverem ativos, 0 caso contrário. Para o domínio hidráulico,
        retorna a pressão média ou uma string de erro/estado de pressurização.

        Returns:
            0 ou 1 para pneumático/elétrico; pressão média (float),
            "ERR" ou "PRESSURIZING" para hidráulico.
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
