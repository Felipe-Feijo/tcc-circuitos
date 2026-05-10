"""
simulation/hydraulic/convergence.py

Monitor de convergência do domínio hidráulico.

Separado do SimulationEngine para permitir testes isolados e
diagnóstico rico sem acoplamento com a lógica de orquestração.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Resultado de convergência
# ---------------------------------------------------------------------------

@dataclass
class ConvergenceResult:
    """
    Resultado da verificação de conservação de vazão.

    Atributos
    ---------
    converged   : True se todos os nós de pressão estão conservados
    imbalances  : {pressure_var: Q_imbalance em m³/s}
    tol         : tolerância usada (m³/s)
    """
    converged: bool
    imbalances: dict[str, float] = field(default_factory=dict)
    tol: float = 0.0

    @property
    def worst_pvar(self) -> str | None:
        """Nó de pressão com maior desequilíbrio."""
        if not self.imbalances:
            return None
        return max(self.imbalances, key=lambda k: abs(self.imbalances[k]))

    @property
    def worst_imbalance(self) -> float:
        """Magnitude do maior desequilíbrio em m³/s."""
        if not self.imbalances:
            return 0.0
        return abs(self.imbalances[self.worst_pvar])

    def summary(self) -> str:
        """Linha de resumo para logging."""
        if self.converged:
            return f"converged (tol={self.tol:.2e} m³/s)"
        return (
            f"NOT converged — worst: {self.worst_pvar} "
            f"ΔQ={self.worst_imbalance:.2e} m³/s "
            f"(tol={self.tol:.2e})"
        )

    def detailed(self) -> str:
        """Diagnóstico detalhado por nó de pressão."""
        if self.converged:
            return "  all pressure nodes conserved"
        lines = []
        for pvar, imb in self.imbalances.items():
            marker = " ← FAIL" if abs(imb) > self.tol else ""
            lines.append(f"  {pvar:50s}  ΔQ = {imb:+.3e} m³/s{marker}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

class ConvergenceMonitor:
    """
    Verifica conservação de vazão em todos os nós de pressão.

    A conservação é verificada nos anchors (resultados escritos após o
    solve), não nas equações do solver — é uma verificação externa e
    independente do NonlinearSystemSolver.

    Parâmetros
    ----------
    tol_factor : fração de q_ref usada como tolerância (default: 1e-4)
                 Ex: q_ref=1e-3 m³/s → tol=1e-7 m³/s
    """

    def __init__(self, tol_factor: float = 1e-4):
        self.tol_factor = tol_factor

    def check(
        self,
        continuities: dict,
        anchor_to_pressure_var: dict,
        q_ref: float,
    ) -> ConvergenceResult:
        """
        Verifica conservação de vazão e retorna ConvergenceResult.

        Parâmetros
        ----------
        continuities          : dicionário de NodeContinuity por pvar
        anchor_to_pressure_var: mapa anchor → pvar (do engine)
        q_ref                 : vazão de referência do circuito
        """
        tol = max(q_ref, 1e-12) * self.tol_factor
        imbalances: dict[str, float] = {}

        for pvar in continuities:
            Q_sum = sum(
                anchor.flow
                for anchor, apvar in anchor_to_pressure_var.items()
                if apvar == pvar
                and isinstance(anchor.flow, (int, float))
            )
            imbalances[pvar] = Q_sum

        converged = all(abs(v) <= tol for v in imbalances.values())
        return ConvergenceResult(converged=converged, imbalances=imbalances, tol=tol)

    def apply_pressurizing_flags(
        self,
        result: ConvergenceResult,
        anchor_to_pressure_var: dict,
    ) -> None:
        """
        Atualiza anchor.pressurizing com base no resultado.
        Separado de check() para manter check() puro (sem side effects).
        """
        for anchor, pvar in anchor_to_pressure_var.items():
            if anchor.domain != "hydraulic":
                continue
            imb = result.imbalances.get(pvar, 0.0)
            anchor.pressurizing = abs(imb) > result.tol