"""NfevScheduler: adaptive least_squares() function-evaluation budget
across the hydraulic domain's zc-escalation retries.

Root cause of the cold-start slowness this replaces: NonlinearSystemSolver
used a flat max_nfev=6000 on every retry. Profiling a real circuit showed
almost every retry burning the FULL 6000-evaluation budget without ever
reaching a good residual (stuck ~5-6e-4) -- 16.8s for a single cold-start
step. Empirically, once zc/x0 are actually close to the true solution, a
real circuit balances to ~1e-11 with as few as 5-10 evaluations; a huge
residual (the current zc/topology guess is fundamentally wrong) never
improves no matter how many more Newton/TRF iterations it's given -- only
the next zc escalation helps. So the budget should stay cheap by default
and only grow when the previous attempt was already close.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.hydraulic.scale_context import NfevScheduler


def test_first_attempt_has_no_previous_residual_uses_cheapest_rung():
    scheduler = NfevScheduler()
    max_nfev, rung = scheduler.advance(rung=0, previous_residual_norm=None)
    assert rung == 0
    assert max_nfev == scheduler.ladder[0]


def test_escalates_one_rung_when_previous_residual_was_close():
    scheduler = NfevScheduler()
    max_nfev, rung = scheduler.advance(
        rung=0, previous_residual_norm=scheduler.close_threshold / 10
    )
    assert rung == 1
    assert max_nfev == scheduler.ladder[1]


def test_resets_to_cheapest_rung_when_previous_residual_was_far():
    scheduler = NfevScheduler()
    max_nfev, rung = scheduler.advance(
        rung=2, previous_residual_norm=scheduler.close_threshold * 100
    )
    assert rung == 0
    assert max_nfev == scheduler.ladder[0]


def test_does_not_escalate_past_the_top_rung():
    scheduler = NfevScheduler()
    top = len(scheduler.ladder) - 1
    max_nfev, rung = scheduler.advance(
        rung=top, previous_residual_norm=scheduler.close_threshold / 10
    )
    assert rung == top
    assert max_nfev == scheduler.ladder[top]


def test_residual_exactly_at_threshold_does_not_count_as_close():
    """Boundary: == threshold is not < threshold -- resets, doesn't escalate."""
    scheduler = NfevScheduler()
    _, rung = scheduler.advance(rung=1, previous_residual_norm=scheduler.close_threshold)
    assert rung == 0


def test_ladder_is_strictly_increasing():
    scheduler = NfevScheduler()
    assert list(scheduler.ladder) == sorted(scheduler.ladder)
    assert len(set(scheduler.ladder)) == len(scheduler.ladder)
