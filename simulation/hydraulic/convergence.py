"""
simulation/hydraulic/convergence.py

Convergence monitor for the hydraulic domain.

Separated from SimulationEngine to allow isolated tests and rich
diagnostics without coupling to the orchestration logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Convergence result
# ---------------------------------------------------------------------------

@dataclass
class ConvergenceResult:
    """
    Result of the flow-conservation check.

    Attributes
    ----------
    converged   : True if every pressure node is conserved
    imbalances  : {pressure_var: Q_imbalance in m3/s}
    tol         : the tolerance used (m3/s)
    """
    converged: bool
    imbalances: dict[str, float] = field(default_factory=dict)
    tol: float = 0.0

    @property
    def worst_pvar(self) -> str | None:
        """The pressure node with the largest imbalance."""
        if not self.imbalances:
            return None
        return max(self.imbalances, key=lambda k: abs(self.imbalances[k]))

    @property
    def worst_imbalance(self) -> float:
        """Magnitude of the largest imbalance in m3/s."""
        if not self.imbalances:
            return 0.0
        return abs(self.imbalances[self.worst_pvar])

    def summary(self) -> str:
        """Summary line for logging."""
        if self.converged:
            return f"converged (tol={self.tol:.2e} m³/s)"
        return (
            f"NOT converged -- worst: {self.worst_pvar} "
            f"dQ={self.worst_imbalance:.2e} m³/s "
            f"(tol={self.tol:.2e})"
        )

    def detailed(self) -> str:
        """Detailed diagnostic per pressure node."""
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
    Checks flow conservation at every pressure node.

    Conservation is checked on the anchors (results written after the
    solve), not on the solver's equations -- it's an external check,
    independent of the NonlinearSystemSolver.

    Parameters
    ----------
    tol_factor : fraction of q_ref used as the tolerance (default: 1e-4)
                 E.g. q_ref=1e-3 m³/s -> tol=1e-7 m³/s
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
        Checks flow conservation and returns a ConvergenceResult.

        Parameters
        ----------
        continuities          : dict of NodeContinuity per pvar
        anchor_to_pressure_var: the engine's anchor -> pvar map
        q_ref                 : the circuit's reference flow
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
        Updates anchor.pressurizing based on the result.
        Separated from check() to keep check() pure (no side effects).
        """
        for anchor, pvar in anchor_to_pressure_var.items():
            if anchor.domain != "hydraulic":
                continue
            imb = result.imbalances.get(pvar, 0.0)
            anchor.pressurizing = abs(imb) > result.tol