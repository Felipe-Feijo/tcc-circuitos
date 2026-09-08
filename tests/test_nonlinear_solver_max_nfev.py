"""NonlinearSystemSolver.solve() must use ctx.max_nfev (from
NfevScheduler) instead of a hardcoded budget, and must expose the
achieved normalized residual afterward so the engine can feed it back
into the NEXT attempt's NfevScheduler.advance() call."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

from simulation.hydraulic.solver import NonlinearSystemSolver
from simulation.hydraulic.scale_context import ScaleContext


class _UnreachableTarget:
    """A single-variable component whose unbounded root is negative, but
    whose bounds forbid it -- forces solve() past fsolve's fast path
    (which would return an out-of-bounds answer) into the least_squares
    fallback, which is the code path that must honor ctx.max_nfev."""
    def __init__(self, var, target):
        self.var = var
        self.target = target

    @property
    def variables(self):
        return [self.var]

    @property
    def bounds(self):
        return {self.var: (0.0, None)}

    def equations(self, x, idx):
        return [x[idx[self.var]] - self.target]


def test_solve_passes_ctx_max_nfev_to_least_squares(monkeypatch):
    import simulation.hydraulic.solver as solver_mod
    real_ls = solver_mod.least_squares
    captured = {}

    def spy_least_squares(*args, **kwargs):
        captured["max_nfev"] = kwargs.get("max_nfev")
        return real_ls(*args, **kwargs)

    monkeypatch.setattr(solver_mod, "least_squares", spy_least_squares)

    comp = _UnreachableTarget("x", target=-1.0)
    solver = NonlinearSystemSolver([comp])
    ctx = ScaleContext(p_ref=1e5, q_ref=1e-4, zc=1e12, max_nfev=42)

    solver.solve({"x": 1.0}, ctx)

    assert captured["max_nfev"] == 42


def test_solve_exposes_last_residual_norm_after_a_call():
    comp = _UnreachableTarget("x", target=-1.0)
    solver = NonlinearSystemSolver([comp])
    ctx = ScaleContext(p_ref=1e5, q_ref=1e-4, zc=1e12, max_nfev=200)

    solver.solve({"x": 1.0}, ctx)

    assert isinstance(solver.last_residual_norm, float)
    assert solver.last_residual_norm >= 0.0


def test_solve_last_residual_norm_is_near_zero_for_an_easy_system():
    """Sanity check: an unconstrained, exactly-solvable system should
    leave last_residual_norm close to zero, not just "some float"."""
    comp = _UnreachableTarget("x", target=5.0)  # within bounds this time
    solver = NonlinearSystemSolver([comp])
    ctx = ScaleContext(p_ref=1e5, q_ref=1e-4, zc=1e12, max_nfev=200)

    sol = solver.solve({"x": 1.0}, ctx)

    assert abs(sol["x"] - 5.0) < 1e-6
    assert solver.last_residual_norm < 1e-6
