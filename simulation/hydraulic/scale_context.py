"""
simulation/hydraulic/scale_context.py

Scale context for the hydraulic domain.

ScaleContext
    Immutable object built once per solve. Carries p_ref, q_ref and
    the zc computed by ZcScheduler. Passed to NodeContinuity and to
    every node via set_scale().

ZcScheduler
    Computes zc (the virtual pressurization capacitor's impedance) as
    a function of the current iteration. zc grows one decade every
    `tau` iterations, anchored on p_ref/q_ref, capped at zc_max.

ScaleManager
    Estimates p_ref and q_ref from the nodes' hints, with memory of
    the last valid scale to survive transitions.

Target operating range: 50-300 bar (5e6-3e7 Pa)
Typical flows: 5-50 L/min (8e-5-8e-4 m3/s)
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Defaults for the industrial hydraulic range (50-300 bar)
# ---------------------------------------------------------------------------

#: Default reference pressure in Pa (~100 bar)
DEFAULT_P_REF: float = 100 * 1e5

#: Default reference flow in m3/s (~20 L/min)
DEFAULT_Q_REF: float = 20 / 60_000

#: zc's base gain: p_ref/q_ref x ZC_BASE_FACTOR
#: Factor 10 positions the virtual capacitor as "moderately stiff"
ZC_BASE_FACTOR: float = 10.0

#: Number of iterations to climb one decade in zc
ZC_TAU: float = 3.0

#: zc's cap, in multiples of zc_base (4 decades)
ZC_MAX_DECADES: float = 4.0


# ---------------------------------------------------------------------------
# ScaleContext
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScaleContext:
    """
    Immutable scale context for one specific solve.

    Created by the engine via ScaleManager.build_context() before
    each call to the solver. Distributed to NodeContinuity and nodes.

    Attributes
    ----------
    p_ref     : reference pressure in Pa
    q_ref     : reference flow in m3/s
    zc        : the virtual capacitor's impedance in Pa*s/m3
    max_nfev  : least_squares() function-evaluation budget for this
                attempt (see NfevScheduler). Defaults to the ladder's
                top rung so code that builds a ScaleContext directly
                (e.g. tests) keeps the old fixed-budget behavior.
    """
    p_ref: float
    q_ref: float
    zc: float
    max_nfev: int = 6000

    def __post_init__(self):
        assert self.p_ref > 0, f"p_ref must be positive, got {self.p_ref}"
        assert self.q_ref > 0, f"q_ref must be positive, got {self.q_ref}"
        assert self.zc > 0,    f"zc must be positive, got {self.zc}"
        assert self.max_nfev > 0, f"max_nfev must be positive, got {self.max_nfev}"

    def __repr__(self) -> str:
        return (
            f"ScaleContext("
            f"p_ref={self.p_ref:.2e} Pa, "
            f"q_ref={self.q_ref:.2e} m³/s, "
            f"zc={self.zc:.2e} Pa·s/m³, "
            f"max_nfev={self.max_nfev})"
        )


# ---------------------------------------------------------------------------
# ZcScheduler
# ---------------------------------------------------------------------------

class ZcScheduler:
    """
    Computes zc as a function of the current iteration.

    Growth: zc(iter) = zc_base x 10^(iter / tau)
    Cap:    zc_max   = zc_base x 10^(ZC_MAX_DECADES)

    zc_base is anchored on p_ref/q_ref x ZC_BASE_FACTOR, guaranteeing
    the virtual capacitor operates on the same scale as the real
    circuit.

    Why grow per iteration?
    ------------------------
    If the circuit hasn't converged (e.g. a relief valve still closed
    when it should open), the pressure needs to rise enough to change
    some component's state. The growing zc progressively increases the
    accumulation's "stiffness", forcing the pressure to rise until the
    topology changes. The 4-decade cap avoids numerical blow-up.

    Parameters
    ----------
    tau           : iterations per decade of zc (default: 3)
    base_factor   : multiplier over p_ref/q_ref (default: ZC_BASE_FACTOR)
    max_decades   : cap in decades above the base (default: ZC_MAX_DECADES)
    """

    def __init__(
        self,
        tau: float = ZC_TAU,
        base_factor: float = ZC_BASE_FACTOR,
        max_decades: float = ZC_MAX_DECADES,
    ):
        self.tau = tau
        self.base_factor = base_factor
        self.max_decades = max_decades

    def zc_base(self, p_ref: float, q_ref: float) -> float:
        """zc at iteration 0, anchored to the circuit's scale."""
        return (p_ref / q_ref) * self.base_factor

    def zc_at(self, iteration: int, p_ref: float, q_ref: float) -> float:
        """
        zc for the given iteration.

        Never drops below zc_base nor rises above
        zc_base x 10^max_decades.
        """
        base = self.zc_base(p_ref, q_ref)
        gain = 10 ** (iteration / self.tau)
        cap  = 10 ** self.max_decades
        return base * min(gain, cap)


# ---------------------------------------------------------------------------
# NfevScheduler
# ---------------------------------------------------------------------------

#: least_squares() max_nfev budget per rung. Deliberately cheap: profiling
#: a real circuit's cold start showed the flat old default (6000) burning
#: the FULL budget on almost every zc-escalation retry without ever
#: reaching a good residual (stuck ~5e-4, 16.8s for one step) -- while a
#: circuit that's actually close to its solution balances to ~1e-11 with
#: as few as 5-10 evaluations. The top rung is a safety net for circuits
#: harder than the ones this was tuned against, not a value expected to
#: be needed often.
DEFAULT_NFEV_LADDER: tuple[int, ...] = (30, 150, 1500)

#: A previous attempt's normalized residual below this is "close enough"
#: to converging that spending more evaluations on the SAME zc is likely
#: to finish the job. At or above it, the zc/topology guess itself is the
#: problem -- more evaluations on it are wasted; only the next zc
#: escalation (or a topology change) helps.
DEFAULT_NFEV_CLOSE_THRESHOLD: float = 1e-2


class NfevScheduler:
    """
    Escalates the least_squares() max_nfev budget across the hydraulic
    domain's zc-escalation retries -- but only when the PREVIOUS
    attempt's normalized residual suggests it was close to converging.

    Unlike ZcScheduler (which grows deterministically with the iteration
    count), this is residual-driven: a huge residual means the current
    zc/topology guess is fundamentally wrong, and no amount of extra
    Newton/TRF iterations fixes that -- only escalating zc does. Only an
    attempt that was already close deserves a bigger budget to finish.

    Parameters
    ----------
    ladder          : max_nfev budget per rung, cheapest first.
    close_threshold : previous normalized residual below this escalates
                       one rung; at or above it, resets to rung 0.
    """

    def __init__(
        self,
        ladder: tuple[int, ...] = DEFAULT_NFEV_LADDER,
        close_threshold: float = DEFAULT_NFEV_CLOSE_THRESHOLD,
    ):
        self.ladder = ladder
        self.close_threshold = close_threshold

    def advance(self, rung: int, previous_residual_norm: float | None) -> tuple[int, int]:
        """
        Resolves the rung to use for this attempt and its max_nfev budget.

        Parameters
        ----------
        rung                    : the rung the previous attempt used (0 if none yet).
        previous_residual_norm  : the previous attempt's normalized residual,
                                   or None if this is the first attempt.

        Returns
        -------
        (max_nfev, rung) : the budget for this attempt, and the rung it
                            was resolved to (persist this for the next call).
        """
        if previous_residual_norm is not None and previous_residual_norm < self.close_threshold:
            rung = min(rung + 1, len(self.ladder) - 1)
        else:
            rung = 0
        return self.ladder[rung], rung


# ---------------------------------------------------------------------------
# ScaleManager
# ---------------------------------------------------------------------------

class ScaleManager:
    """
    Estimates p_ref and q_ref from the hydraulic nodes' hints.

    Cascading strategy for p_ref:
      1. max of the nodes' p_hint (if any > 1 Pa)
      2. inference via the `pressure` attribute (a Reservoir with P > 0)
      3. memory of the last valid scale (EMA over real results)
      4. absolute fallback: DEFAULT_P_REF

    Cascading strategy for q_ref:
      1. max of the nodes' flow_hint (if any > 1e-10)
      2. memory of the last valid scale (EMA over real results)
      3. absolute fallback: DEFAULT_Q_REF

    The memory uses an EMA (exponential moving average) over the
    previous solution's real values -- not just the nodes' static
    hints. This keeps the scaling tracking the circuit's real state
    after topology transitions (a valve commutates, a cylinder hits an
    end stop), where the hints can go stale for several iterations.

    Parameters
    ----------
    ema_alpha : weight of the new value in the EMA (0 < alpha <= 1).
                Alpha=1 disables the memory (original behavior).
                Alpha=0.2 gives 80% weight to history -- smooth tracking.
    """

    #: EMA weight for updates from the solve's real results
    EMA_ALPHA: float = 0.2

    def __init__(self):
        self._last_p: float = DEFAULT_P_REF
        self._last_q: float = DEFAULT_Q_REF

    def estimate(self, nodes: list) -> tuple[float, float]:
        """
        Returns (p_ref, q_ref) in Pa and m3/s.

        Updates the internal memory if the estimated values are valid.
        """
        p_ref = self._estimate_pressure(nodes)
        q_ref = self._estimate_flow(nodes)

        # only updates the memory when we have trustworthy values from the hints
        if p_ref > 1.0:
            self._last_p = p_ref
        if q_ref > 1e-10:
            self._last_q = q_ref

        return p_ref, q_ref

    def update_from_solution(self, sol: dict[str, float]) -> None:
        """
        Updates the scale memory with an EMA over the last successful
        solve's real results.

        Should be called by the engine after each accepted solve,
        before discarding the solution. This closes the feedback loop:
        instead of relying only on static hints, the scaling learns
        from the real values the solver found.

        Parameters
        ----------
        sol : {variable_name: value} dict returned by the solver
        """
        p_values = [v for k, v in sol.items()
                    if k.startswith("P_") and isinstance(v, float) and v > 1.0]
        q_values = [abs(v) for k, v in sol.items()
                    if k.startswith("Q_") and isinstance(v, float) and abs(v) > 1e-10]

        alpha = self.EMA_ALPHA

        if p_values:
            p_real = max(p_values)
            self._last_p = (1.0 - alpha) * self._last_p + alpha * p_real

        if q_values:
            q_real = max(q_values)
            self._last_q = (1.0 - alpha) * self._last_q + alpha * q_real

    def build_context(
        self,
        nodes: list,
        iteration: int,
        scheduler: ZcScheduler | None = None,
        max_nfev: int | None = None,
    ) -> ScaleContext:
        """
        Builds a complete ScaleContext for the current solve.

        Parameters
        ----------
        nodes     : list of the circuit's HydraulicNode instances
        iteration : the current hydraulic convergence loop's iteration
        scheduler : a custom ZcScheduler (uses the default if None)
        max_nfev  : least_squares() budget for this attempt (see
                    NfevScheduler). Uses ScaleContext's own default when
                    None -- callers that don't manage an NfevScheduler
                    (e.g. tests building a ScaleContext for a single,
                    known-easy solve) get the old fixed-budget behavior.
        """
        if scheduler is None:
            scheduler = ZcScheduler()

        p_ref, q_ref = self.estimate(nodes)
        zc = scheduler.zc_at(iteration, p_ref, q_ref)

        kwargs = {"p_ref": p_ref, "q_ref": q_ref, "zc": zc}
        if max_nfev is not None:
            kwargs["max_nfev"] = max_nfev
        return ScaleContext(**kwargs)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _estimate_pressure(self, nodes: list) -> float:
        # 1. the nodes' explicit hints
        hints = [
            n.p_hint for n in nodes
            if hasattr(n, "p_hint") and isinstance(n.p_hint, (int, float))
            and n.p_hint > 1.0
        ]
        if hints:
            return max(hints)

        # 2. inference via a Reservoir or a node with fixed pressure
        inferred = [
            n.pressure for n in nodes
            if hasattr(n, "pressure")
            and isinstance(n.pressure, (int, float))
            and n.pressure > 1.0
        ]
        if inferred:
            return max(inferred)

        # 3. memory
        return self._last_p

    def _estimate_flow(self, nodes: list) -> float:
        hints = [
            n.flow_hint for n in nodes
            if hasattr(n, "flow_hint") and isinstance(n.flow_hint, (int, float))
            and n.flow_hint > 1e-10
        ]
        if hints:
            return max(hints)

        # memory
        return self._last_q