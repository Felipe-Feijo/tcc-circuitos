"""
simulation/hydraulic/node_protocol.py

Contrato formal para nós do domínio hidráulico.

Convenção de sinal (adotada em todo o domínio):
  Q > 0  =>  fluido ENTRANDO no nó pela porta
  Q < 0  =>  fluido SAINDO  do nó pela porta

Todo nó hidráulico deve herdar de HydraulicMixin e implementar
os métodos abstratos: variables, hydraulic_ports, equations.

O HydraulicNode Protocol permite isinstance() check sem herança,
mas a detecção real do engine usa HydraulicMixin como base.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
import numpy as np


@runtime_checkable
class HydraulicNode(Protocol):
    """
    Protocol estrutural — permite isinstance(node, HydraulicNode).
    Verificado em runtime pelo engine para coletar nós hidráulicos.

    Implementação mínima: variables, hydraulic_ports, equations.
    Defaults para o resto: use HydraulicMixin como base na sua classe.
    """

    @property
    def variables(self) -> list[str]: ...
    def hydraulic_ports(self) -> dict[str, str]: ...
    def equations(self, x: np.ndarray, idx: dict[str, int]) -> list[float]: ...
    def set_scale(self, p_ref: float, q_ref: float) -> None: ...

    @property
    def flow_hint(self) -> float: ...
    @property
    def p_hint(self) -> float: ...
    @property
    def bounds(self) -> dict: ...
    @property
    def initial_guess(self) -> dict: ...


class HydraulicMixin:
    """
    Mixin com implementações default para membros opcionais do contrato.

    Uso:
        class MinhaValvula(Node, HydraulicMixin):
            ...  # só precisa implementar variables, hydraulic_ports, equations

    Membros com default (pode sobrescrever):
        bounds        → {} (sem bounds)
        set_scale     → armazena p_ref/q_ref em self.p_ref / self.q_ref
        flow_hint     → 0.0
        p_hint        → 0.0
        initial_guess → {}

    Membros obrigatórios (deve implementar):
        variables      (property)
        hydraulic_ports (método)
        equations       (método)
    """

    # Escala default para a faixa industrial (50–300 bar)
    # Sobrescrito por set_scale() antes de cada solve
    p_ref: float = 100 * 1e5   # Pa — 100 bar
    q_ref: float = 20 / 60_000  # m³/s — 20 L/min

    @property
    def bounds(self) -> dict[str, tuple[float | None, float | None]]:
        """Sem bounds por padrão."""
        return {}

    def set_scale(self, p_ref: float, q_ref: float) -> None:
        """Armazena p_ref e q_ref para uso em equations()."""
        self.p_ref = max(p_ref, 1e5)    # mínimo 1 bar
        self.q_ref = max(q_ref, 1e-10)

    @property
    def flow_hint(self) -> float:
        """Estimativa de vazão característica. Override para melhor scaling."""
        return 0.0

    @property
    def p_hint(self) -> float:
        """Estimativa de pressão característica. Override para melhor scaling."""
        return 0.0

    @property
    def initial_guess(self) -> dict[str, float]:
        """Chute inicial vazio — solver usa Q_hint global."""
        return {}