"""
simulation/hydraulic/solver.py

Nonlinear solver for hydraulic circuits.

Contents
--------
NodeContinuity        : accumulation equation per pressure node
NonlinearSystemSolver : builds and solves the equation system

This module replaces simulation/hydraulic_solver.py (removed).
"""

from __future__ import annotations

import math
import numpy as np
from scipy.optimize import fsolve, least_squares

from simulation.hydraulic.scale_context import ScaleContext


# ---------------------------------------------------------------------------
# NodeContinuity -- virtual pressurization capacitor
# ---------------------------------------------------------------------------

class NodeContinuity:
    """
    Accumulation equation for a pressure node.

    Models a virtual hydraulic capacitor that balances flow imbalances
    by accumulating pressure. Serves two purposes:

      1. Numerical: closes the equation system (a pressure node not
         connected to a source would need an extra equation).

      2. Pressurization: if the circuit doesn't converge (e.g. a relief
         valve stuck closed when it should open), the growing zc forces
         the pressure to rise until the topology changes -- see
         ZcScheduler.

    Equation:
        Q_sum - (P - P_prev) / zc = 0

    Where:
        Q_sum  = algebraic sum of flows at the node (positive = inflow)
        P      = current pressure at the node
        P_prev = pressure from the previous iteration (memory)
        zc     = capacitor impedance [Pa*s/m3]

    Parameters
    ----------
    pressure_var : the node's pressure variable name
    flow_vars    : list of connected flow variable names
    """

    def __init__(self, pressure_var: str, flow_vars: list[str]):
        self.pressure_var = pressure_var
        self.flow_vars = flow_vars

        self.p_previous: float = 0.0
        self._ctx: ScaleContext | None = None

    @property
    def variables(self) -> list[str]:
        return [self.pressure_var]

    @property
    def bounds(self) -> dict[str, tuple[float | None, float | None]]:
        return {self.pressure_var: (0.0, None)}  # pressure is never negative

    def apply_context(self, ctx: ScaleContext) -> None:
        """Receives the ScaleContext before each solve."""
        self._ctx = ctx

    def equations(self, x: np.ndarray, idx: dict[str, int]) -> list[float]:
        assert self._ctx is not None, "apply_context() was not called before equations()"
        P     = x[idx[self.pressure_var]]
        Q_sum = -sum(x[idx[q]] for q in self.flow_vars if q in idx)
        # normalized by q_ref to keep the equation dimensionless
        return [(Q_sum - (P - self.p_previous) / self._ctx.zc) / self._ctx.q_ref]

    def update_pressure(self, sol: dict[str, float]) -> None:
        """
        Updates P_prev after a successful solve.
        Numerical-noise values are discarded.
        """
        if self.pressure_var not in sol:
            return
        new_p = sol[self.pressure_var]
        assert self._ctx is not None
        noise_threshold = self._ctx.q_ref * self._ctx.zc * 1e-6
        self.p_previous = 0.0 if new_p < noise_threshold else new_p

    def reset(self) -> None:
        """Resets the pressure memory (topology change)."""
        self.p_previous = 0.0


# ---------------------------------------------------------------------------
# NonlinearSystemSolver
# ---------------------------------------------------------------------------

class NonlinearSystemSolver:
    """
    Builds and solves the circuit's nonlinear equation system.

    Dual strategy:
      1. Fast attempt with fsolve (Newton-Raphson) -- no bounds.
         Accepted if: converged + residual ok + within bounds + no blow-up.
      2. Robust fallback with least_squares (TRF) -- respects bounds.
         Uses fsolve's best result as a warm start (if reasonable).

    Parameters
    ----------
    components : list of objects with a {variables, equations, bounds}
                 interface (HydraulicNode + NodeContinuity)
    """

    def __init__(self, components: list):
        self.components = components
        self.var_index: dict[str, int] = {}
        self.index_var: list[str] = []

    def register_variables(self) -> None:
        for comp in self.components:
            for var in comp.variables:
                if var not in self.var_index:
                    self.var_index[var] = len(self.index_var)
                    self.index_var.append(var)

    def build_bounds(self) -> tuple[np.ndarray, np.ndarray]:
        lower = np.full(len(self.index_var), -np.inf)
        upper = np.full(len(self.index_var),  np.inf)

        for comp in self.components:
            if not hasattr(comp, "bounds"):
                continue
            for var, (lo, hi) in comp.bounds.items():
                if var not in self.var_index:
                    continue
                idx = self.var_index[var]
                if lo is not None:
                    lower[idx] = lo
                if hi is not None:
                    upper[idx] = hi

        return lower, upper

    def build_system(self):
        def system(x):
            eqs = []
            for comp in self.components:
                eqs.extend(comp.equations(x, self.var_index))
            return eqs
        return system

    def solve(
        self,
        x0_dict: dict[str, float],
        ctx: ScaleContext,
    ) -> dict[str, float]:
        """
        Solves the system and returns {variable: value}.

        Parameters
        ----------
        x0_dict : initial guess per variable name
        ctx     : the current circuit's ScaleContext
        """
        self.register_variables()

        x0 = np.zeros(len(self.index_var))
        for var, val in x0_dict.items():
            if var in self.var_index:
                x0[self.var_index[var]] = val

        lower, upper = self.build_bounds()
        x0 = np.clip(x0, lower, upper)

        system = self.build_system()
        q_ref_safe = max(ctx.q_ref, 1e-12)

        # Mixed normalization scale for fsolve's acceptance criterion.
        # The system has two equation classes with different units:
        #   - flow equations (NodeContinuity, conservation): residual in m3/s
        #   - pressure equations (valve dP-Q, etc.): residual in Pa
        # Using only q_ref as the threshold would silently accept
        # solutions where the pressure equations have a huge residual
        # (e.g. 1e5 Pa). The mixed scale normalizes both classes to
        # order 1.
        _mixed_scale = q_ref_safe + ctx.p_ref / max(ctx.zc, 1.0)

        # ------------------------------------------------------------------ #
        # Fast attempt -- fsolve (Newton-Raphson)                              #
        # ------------------------------------------------------------------ #
        x_for_ls = x0.copy()
        fsolve_best: np.ndarray | None = None   # fsolve's best solution, even outside bounds
        fsolve_best_residual = np.inf

        try:
            x_fast, info, ier, msg = fsolve(system, x0.copy(), full_output=True)
            residual_fast = np.max(np.abs(info["fvec"]))

            within_bounds = (
                np.all(x_fast >= lower - 1e-10) and
                np.all(x_fast <= upper + 1e-10)
            )
            sane = np.all(np.abs(x_fast) < 1e12)

            # Normalized criterion: dimensionless residual < 1e-6.
            residual_norm = residual_fast / _mixed_scale
            if ier == 1 and residual_norm < 1e-6 and within_bounds and sane:
                print(f"  fsolve: converged | residual_norm={residual_norm:.2e} (raw={residual_fast:.2e})")
                return {var: x_fast[i] for var, i in self.var_index.items()}

            if sane:
                x_for_ls = x_fast  # warm start for least_squares
                # Keeps this as a fallback candidate even outside bounds --
                # if least_squares fails, this solution may be better than nothing.
                if ier == 1 and residual_norm < 1e-4:
                    fsolve_best = np.clip(x_fast, lower, upper)
                    fsolve_best_residual = residual_fast

        except Exception as e:
            print(f"  fsolve: exception -- {e}")

        # ------------------------------------------------------------------ #
        # Robust fallback -- least_squares (TRF)                              #
        # ------------------------------------------------------------------ #
        x_for_ls = np.clip(x_for_ls, lower, upper)

        # Explicit per-variable-type scale: P-vars in Pa, Q-vars in m3/s.
        # We avoid x_scale="jac" because a hydraulic circuit's Jacobian is
        # often ill-conditioned (P/Q ratio ~1e8 at 100 bar / 20 L/min),
        # and Jacobian-based scaling inherits that ill-conditioning
        # instead of fixing it. With an explicit physical scale, TRF
        # operates on dimensionless order-1 variables, converging faster
        # and more robustly.
        x_scale_arr = np.array([
            ctx.p_ref if var.startswith("P_") else ctx.q_ref
            for var in self.index_var
        ])
        x_scale_arr = np.where(x_scale_arr > 0, x_scale_arr, 1.0)

        result = least_squares(
            system, x_for_ls,
            method="trf",
            bounds=(lower, upper),
            x_scale=x_scale_arr,
            ftol=1e-10,
            xtol=1e-10,
            gtol=1e-10,
            max_nfev=6000,
        )

        residual = np.max(np.abs(result.fun))
        print(
            f"  least_squares: {result.message} | "
            f"residual={residual:.2e} | "
            f"p_ref={ctx.p_ref:.2e} Pa | "
            f"q_ref={ctx.q_ref:.2e} m³/s | "
            f"zc={ctx.zc:.2e}"
        )

        # If least_squares didn't converge well but fsolve had a
        # reasonable solution (even outside bounds because of the stops),
        # prefer fsolve. This keeps the engine from receiving a garbage
        # TRF solution and flagging ERR.
        ls_residual_norm = residual / _mixed_scale
        if ls_residual_norm > 1e-4 and fsolve_best is not None:
            if fsolve_best_residual / _mixed_scale < ls_residual_norm:
                print(f"  least_squares: falling back to fsolve (lower residual)")
                return {var: fsolve_best[i] for var, i in self.var_index.items()}

        return {var: result.x[i] for var, i in self.var_index.items()}

    def build_initial_guess(
        self,
        hydraulic_nodes: list,
        ctx: ScaleContext,
    ) -> dict[str, float]:
        """
        Builds the initial guess by combining:
          - the nodes' initial_guess (takes precedence)
          - the global Q_hint for flow variables with no guess
        """
        x0: dict[str, float] = {
            var: 0.0
            for node in hydraulic_nodes
            for var in node.variables
        }

        guessed_vars: set[str] = set()
        for node in hydraulic_nodes:
            if hasattr(node, "initial_guess"):
                guess = node.initial_guess
                x0.update(guess)
                guessed_vars.update(guess.keys())

        # scales the sign sentinels (+-1.0) to Q_hint
        for var in x0:
            if not var.startswith("Q_"):
                continue
            if var not in guessed_vars and x0[var] == 0.0:
                x0[var] = ctx.q_ref
            elif var in guessed_vars and abs(x0[var]) == 1.0:
                x0[var] = math.copysign(ctx.q_ref, x0[var])

        return x0