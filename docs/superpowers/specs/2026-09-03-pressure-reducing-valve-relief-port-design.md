# Pressure reducing valve — relief port (3-way variant) — design

Date: 2026-09-03 (equations revised same day after a failed first
implementation attempt — see "Design history" below)
Status: equations redesigned and numerically spike-tested (cold-start
convergence confirmed in a standalone script, not yet wired into the
codebase). Approved for a fresh implementation plan. The graphics item,
property, and port sections below are UNCHANGED from the first attempt
and remain valid — only "Equations" is new.

## Context and problem

`2026-09-03-pressure-reducing-valve-design.md` shipped the single-stage,
2-port (`P`/`A`) pressure reducing valve, explicitly deferring the
"reducing-and-relieving" 3-way variant to a follow-up spec — same
incremental path `ReliefValve` took (base direct-acting version first, then
a separate spec for its external pilot).

The 2-port valve has a known limitation, documented in that base spec's
addendum: when something external pushes the outlet (`P_A`) above `p_set`
with no forward flow happening (`Q_P <= 0`), the valve can only refuse
more inflow (`Q_P = 0`) — it has no way to bleed the excess back down,
since it has nowhere to send it. This spec adds that path: an optional
`T` port that lets the valve actively hold `P_A` at `p_set` from above,
not just refuse to make it worse.

## Property and port

New property: `relieving: bool = False` (same shape as `ReliefValve`'s
`piloted`). When `True`, adds anchor `T` — a real flow port (unlike
`ReliefValve`'s `piloted` `Y`, which is a dead sensing-only port, `T`
here carries real flow to whatever `Reservoir` the user wires it to,
exactly like `ReliefValve`'s own `T` port already does).

`T`'s bounds: `(None, 0.0)` — flow only ever leaves through `T` (same
convention as `ReliefValve.bounds[flow_var_out]`).

`A`'s bounds change under `relieving=True`: relief requires flow entering
at `A` (domain convention: `Q > 0` means entering), so `A` becomes
bidirectional (`None, None`) instead of the 2-port valve's `(None, 0.0)`.
This was missed in the first pass of this spec (the original text below
only ever discussed `T`'s bounds) and caused the Critical bug described
in "Design history" below.

Every tank port in this codebase (including `ReliefValve`'s own `T`)
requires the user to wire it to a `Reservoir` node, whose own
`equations()` is what actually fixes that pressure variable
(`simulation/nodes/reservoir.py:30-33`, `P_T = self.pressure`, normally
0). This valve's `T` is no different — there is no "implicit tank" mode.

An unconnected `T` does NOT leave the system underdetermined —
`NodeContinuity` gives even a lone anchor its own pressure group and
equation (same mechanism as any node with no other equation referencing
its pressure variable), so the solve stays square. The problem is
physical, not numerical: the valve relieves into a pressure that has no
real meaning (nothing enforces it beyond an arbitrary starting seed),
producing a solvable but nonsensical result. As with `ReliefValve`'s own
`T` port (which has no connectivity guard either), correctness depends on
the user actually wiring `T` to a real `Reservoir` — this is a modeling
convention, not something the solver enforces.

## Equations

**This section supersedes an earlier, shipped-then-reverted design.**
See "Design history" below for what was tried first, why it failed in
the real solver, and how that failure was root-caused. The formulation
below was numerically validated in a standalone spike script (cold
start, 8 scenarios including stress cases) before being written here —
see "Validation" below.

Conservation becomes 3-port when `relieving=True`:
`Q_P + Q_A + Q_T = 0` (was `Q_P + Q_A = 0`), unchanged from the first
attempt. `variables`, `hydraulic_ports`, `bounds` all conditionally
include the `T` entries only when `relieving=True` — same
conditional-inclusion pattern `ReliefValve` already uses for `piloted`'s
`Y`. The `relieving=False` path is UNCHANGED from what already shipped
(byte-identical 2-port equations).

The `relieving=True` path replaces the old hard branch with a dual
Fischer-Burmeister pairing that shares the same cap term, plus two small
correction terms that make it actually well-posed:

```python
PENALTY_WEIGHT = 500.0
RIDGE_WEIGHT = 0.0015

def _smooth_max0(z, eps=1e-9):
    return (z + math.sqrt(z * z + eps * eps)) / 2.0

def equations(self, x, idx):
    Q_p = x[idx[self.flow_var_p]]
    Q_a = x[idx[self.flow_var_a]]
    P_p = x[idx[self.anchors["P"].pressure_var]]
    P_a = x[idx[self.anchors["A"].pressure_var]]
    Q_scale, P_scale = self.q_ref, self.p_ref

    if not self.relieving:
        eq_conservation = (Q_p + Q_a) / Q_scale
        a = (self.p_set - P_a) / P_scale
        b = (P_p - P_a) / P_scale
        eq_supply = a + b - math.sqrt(a * a + b * b)   # unchanged from the 2-port valve
        return [eq_conservation, eq_supply]

    Q_t = x[idx[self.flow_var_t]]
    eq_conservation = (Q_p + Q_a + Q_t) / Q_scale

    a = (self.p_set - P_a) / P_scale               # shared cap term

    b_supply = (P_p - P_a) / P_scale
    eq_supply = a + b_supply - math.sqrt(a * a + b_supply * b_supply)
    # Reverse-flow exclusion: fsolve's own unbounded stage ignores
    # `bounds` entirely and converges onto Q_p<0 with a genuinely tiny
    # residual (this is the exact mechanism that broke the first
    # attempt -- see "Design history"). This penalty makes that root
    # expensive at the EQUATION level, not just via `bounds`.
    eq_supply += _smooth_max0(-Q_p / Q_scale) * PENALTY_WEIGHT

    b_relief = -Q_t / Q_scale
    eq_relief = a + b_relief - math.sqrt(a * a + b_relief * b_relief)
    # Tie-break: at the shared root (a=0, i.e. P_a=p_set), both
    # eq_supply and eq_relief individually admit Q_p>=0 and Q_t<=0
    # simultaneously free -- rank-deficient without this (confirmed in
    # the spike: without the ridge, "regulating" converged with a
    # spurious nonzero Q_t even though supply alone could handle it
    # fully). This small ridge pulls Q_t toward 0 unless relief is
    # genuinely needed to hold the cap.
    eq_relief += RIDGE_WEIGHT * (Q_t / Q_scale)

    return [eq_conservation, eq_supply, eq_relief]
```

**Why the dual-FB shape itself is fine (only the naive version wasn't):**
both `eq_supply` and `eq_relief` share the exact same cap term `a`, so
at `a=0` (`P_A=p_set`) they are individually satisfied by any split of
`Q_p>=0`/`Q_t<=0` that balances conservation — genuinely rank-deficient
as a bare pair. The ridge term breaks that tie without perturbing the
"genuinely needs relief" case (where `Q_t`'s magnitude, e.g. `-1e-4`, is
far larger than what a `0.0015` ridge could suppress). Both weights were
tuned empirically against the spike's scenarios, not derived from first
principles.

## Validation

Tested in a standalone spike script (not part of the codebase — throwaway,
not committed) against `scipy.optimize.fsolve`/`least_squares`, mimicking
`simulation/hydraulic/solver.py`'s two-stage solve (unbounded `fsolve`
first, bounded TRF fallback, including the real `fsolve_best` clip
behavior) from a cold start (`x0 = [0, 0, 0]`, matching how the real
engine seeds every pressure at 0). 8 scenarios: fully open, regulating
via supply, relieving via tank, idle, relief at 5x and at 1/100x the
baseline flow, regulating against a very high supply pressure, and
relieving with the supply side fully disconnected (`P_p=0`).

6 of 8 converged to the physically correct answer within realistic
tolerance (flow within 1%, `P_A` within `rel=1e-3` of `p_set` — the same
tolerance the real end-to-end test uses). The 2 that didn't were both
relief flows far smaller than the spike's fixed flow scale (`1e-6`
against a baseline of `1e-4`) — see "Remaining known limitation" below.

## Remaining known limitation

`PENALTY_WEIGHT`/`RIDGE_WEIGHT` are dimensionless multipliers on
already-`Q_scale`-normalized terms, but the spike only validated them
against flows comparable to its fixed baseline. A relief flow much
smaller than the circuit's actual `q_ref` (not just smaller than a
fixed spike constant) may need retuned weights, or a more principled
scale-adaptive version of the same terms. The follow-up implementation
plan MUST include an end-to-end solver test (not just `equations()`
called in isolation — see "Design history" for why that gap let the
first attempt ship broken) covering at least the "relieving" scenario at
the flow magnitude the real engine actually seeds circuits at, and
should treat weight-tuning as part of that test's acceptance criteria,
not a one-time guess.

This is independent of, and does not fix, the separately-discovered
`simulation/hydraulic/solver.py` `fsolve_best`/`fsolve_best_residual`
mismatch (the clipped point and the reported residual come from
different, unclipped-vs-clipped values) — that bug is out of scope for
this spec but affects how confidently any hydraulic node's near-boundary
behavior can be trusted; worth its own fix.

## Design history: why the branch-guard approach failed

This is the FIRST design attempted, shipped, and then reverted after its
final review found it non-functional. Kept here as the record of what
was tried and why — the current design above avoids all three problems
identified.

```python
# ORIGINAL (do not use):
if P_a > self.p_set and Q_p <= 0:
    eq_supply = Q_p / Q_scale
    if self.relieving:
        eq_relief = (P_a - self.p_set) / P_scale
else:
    a = (self.p_set - P_a) / P_scale
    b = (P_p - P_a) / P_scale
    eq_supply = a + b - sqrt(a*a + b*b)
    if self.relieving:
        eq_relief = Q_t / Q_scale
```

Verified mechanism (re-derived independently, not just the first
implementer's guess — an earlier attempt at this diagnosis attributed it
to the wrong cause, see the re-review report for the correction):

- The solver's cold start seeds every pressure at 0 (`p_previous`
  continuity-based seeding is unreachable dead code at
  `simulation_engine.py:680-683` — it never runs before `solve()`
  populates `var_index`), so the relief branch (`P_a > p_set`) is never
  entered in the first place.
- `fsolve` instead converges — with `ier=1` and a genuinely tiny
  residual (~1e-17) — onto a *different*, bound-violating root: the
  fully-open regime with the pump's flow running backwards through the
  valve into the `P`-side reservoir (`Q_P` negative, violating `Q_P>=0`).
  Bounds do not stop `fsolve` from finding this point — `fsolve` ignores
  bounds entirely.
- That point is correctly rejected by the engine's own `within_bounds`
  check, but an independent, pre-existing bug in
  `simulation/hydraulic/solver.py` (the `fsolve_best` fallback stores
  `np.clip(x_fast, lower, upper)` while keeping the *unclipped* point's
  residual) makes the engine report a falsely-tiny residual for the
  clipped, physically-wrong answer instead of failing loudly.
- Even fixing the above, the relief branch's own root sits exactly on
  its guard's boundary (`P_a > p_set`, strict), and that boundary
  coincides with `Q_P`'s own active lower bound (`Q_P<=0` required by
  the guard vs. `Q_P>=0` required by the node's bounds) — the branch is
  reachable only on a measure-zero slice of the feasible set, which a
  derivative-based solver's finite-difference Jacobian cannot reliably
  approach (confirmed: forward- and backward-difference stencils at that
  corner disagree by ~8 orders of magnitude in one column). Loosening
  the guard from `>` to `>=` does not fix this corner problem.

**Three requirements this design history handed to the redesign above —
each is addressed in "Equations":**

1. Replace the hard branch guard with a smooth formulation → done: the
   dual-FB pairing has no hard branch at all, `relieving=True` is always
   evaluated the same way regardless of trial `P_a`/`Q_p`.
2. Decouple from `Q_P`'s active bound → done: the reverse-flow penalty
   makes `Q_p<0` expensive continuously, not via a guard condition that
   could coincide with the bound edge.
3. Exclude the reverse-flow root with an equation, not just `bounds` →
   done: `_smooth_max0(-Q_p/Q_scale) * PENALTY_WEIGHT` is exactly this,
   added directly into `eq_supply`'s residual.

The `solver.py` clip/residual mismatch remains a separate, pre-existing
defect independent of this feature (any node encoding physics in
`bounds` rather than `equations()` is exposed to it) — worth its own
fix, still out of scope for this spec.

## Graphics item

Sprite: `resources/nodes/pressure_reducing_valve/pressure_reducing_valve_relief.png`
(already created), 200×162px, transparent overlay drawn on top of the
existing body sprite only when `relieving=True` — same overlay mechanism
as `ReliefValve`'s `relief_valve_pilot.png` (`_pilot_overlay` /
`_update_pilot_anchor()` pattern in `graphics/items/base/nodes/relief_valve.py`).

Anchor, measured from the overlay's opaque pixels (line reaches the
bottom edge at x=132..137, center 134.5):

| Anchor | Position                     | Exit direction |
|--------|-------------------------------|-----------------|
| T      | `(width*134.5/200, height)`   | bottom          |

Does not collide with the existing `A` anchor (`x=width*98.5/200`, also
bottom) — different x columns on the same edge, same as how other
multi-port components place several anchors on one side.

Properties dialog: adds a checkbox labeled **"Tank port (T)"** (not
"Relief to tank" — the port is just wired to whatever the user connects,
same wording rationale as why the base spec avoided asserting the tank
connection is automatic). Same show/hide-on-toggle pattern already used
elsewhere (e.g. `check_valve`'s `pilot_exit` combo, `ReliefValve`'s
`piloted` checkbox).

## Non-goals (unchanged from the base spec, still deferred)

- External/remote pilot setpoint (a `Y`-style port adjusting `p_set`
  from an external pressure). Explicitly discussed and deferred again —
  no concrete use case yet; will get its own spec if/when needed, same
  incremental path.
- Reverse flow / integrated check function through the `P`/`A` pair
  itself. Still out of scope — `A` becoming bidirectional under
  `relieving=True` lets flow enter at `A` and leave via `T`, but the
  reverse-flow penalty in "Equations" specifically keeps `Q_P>=0`
  always, so that flow never goes back out through `P`. `A→T` is a new
  path; `A→P` is not reopened.
- Pneumatic domain.

## Files

- `simulation/nodes/pressure_reducing_valve.py` — modified: `relieving`
  property, `T` port, `A`'s bounds, and `equations()` all already exist
  from the first (reverted-in-spirit but still-committed) attempt;
  `equations()`'s `relieving=True` body must be REPLACED with the
  dual-FB formulation above, not added alongside it.
- `graphics/items/base/nodes/pressure_reducing_valve.py` — unchanged
  from the first attempt (the graphics/overlay/dialog work was already
  correct and separately reviewed clean; only the simulation node's
  physics needs redoing).
- `tests/test_pressure_reducing_valve_hydraulic.py` — the
  `relieving=True` tests from the first attempt
  (`test_relief_regime_residual_matches_formula`,
  `test_relief_regime_residual_shrinks_to_near_zero_as_p_a_approaches_p_set`,
  `test_relief_port_is_dead_when_not_in_closed_branch`) assert against
  the OLD branch-guard formula and must be REMOVED, not kept alongside
  new ones — they test a formula that no longer exists.
  `test_relieving_false_by_default_no_t_port`,
  `test_relieving_true_adds_t_port`,
  `test_variables_include_t_flow_and_pressure_when_relieving`,
  `test_bounds_include_t_when_relieving`,
  `test_relieving_conservation_is_3_port`, and
  `test_initial_guess_seeds_t_flow_when_relieving` test
  shape/bounds/conservation, not the specific formula — these stay.
  The end-to-end test
  (`test_relief_regime_holds_outlet_at_p_set_end_to_end`) stays, with
  its `xfail` marker REMOVED (it must actually pass now — this is the
  test that catches a repeat of this whole failure).
- `tests/test_pressure_reducing_valve_item.py` — unchanged, no new
  tests needed (nothing here depends on the equation formulation).
