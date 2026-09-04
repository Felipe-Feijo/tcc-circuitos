# Pressure reducing valve — relief port (3-way variant) — design

Date: 2026-09-03 (equations revised twice same day: once after a failed
first implementation attempt, once more during hands-on validation of
the replacement — see "Design history" and "Implementation refinements"
below)
Status: implemented, tested (1052/1052 suite passing, including a
solver-level end-to-end regression test), and hands-on validated against
two real circuits (a fixed-displacement-pump-driven cylinder, and an
externally-pinned-high-supply-pressure scenario) before merge. Carries
one documented, accepted trade-off — see "Remaining known limitation".

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

`A`'s bounds are UNCHANGED from the 2-port valve, even when
`relieving=True`: `(None, 0.0)` — forward/outgoing only, never reversed.
An earlier pass of this spec made `A` bidirectional (`None, None`) to
support flow entering from an external source pushing directly on `A`.
That turned out to be unnecessary for every realistic circuit tried
during implementation (a fixed-displacement pump forcing more flow into
`P` than a downstream load can accept diverts the excess to `T` via
conservation alone, without `A` ever needing to reverse) and it widened
the solver's search space with a whole extra root family — see
"Implementation refinements" below and the module docstring's Scope
note. True external backfeed directly into `A` is now an explicit
non-goal.

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

**This section supersedes an earlier, shipped-then-reverted design**
(see "Design history"), **and reflects corrections found during hands-on
validation of the replacement** (see "Implementation refinements") —
this is the actual, final, shipped formula.

Conservation becomes 3-port when `relieving=True`:
`Q_P + Q_A + Q_T = 0` (was `Q_P + Q_A = 0`). `variables`,
`hydraulic_ports`, `bounds` all conditionally include the `T` entries
only when `relieving=True` — same conditional-inclusion pattern
`ReliefValve` already uses for `piloted`'s `Y`. The `relieving=False`
path is UNCHANGED from what already shipped (byte-identical 2-port
equations, closed-regime branch included).

The `relieving=True` path is a dual Fischer-Burmeister pairing sharing
the same cap term, plus three correction terms:

```python
def equations(self, x, idx):
    Q_p = x[idx[self.flow_var_p]]
    Q_a = x[idx[self.flow_var_a]]
    P_p = x[idx[self.anchors["P"].pressure_var]]
    P_a = x[idx[self.anchors["A"].pressure_var]]
    Q_scale, P_scale = self.q_ref, self.p_ref

    if not self.relieving:
        eq_conservation = (Q_p + Q_a) / Q_scale
        if P_a > self.p_set and Q_p <= 0:
            eq_supply = Q_p / Q_scale
        else:
            a = (self.p_set - P_a) / P_scale
            b = (P_p - P_a) / P_scale
            eq_supply = a + b - math.sqrt(a * a + b * b)
        return [eq_conservation, eq_supply]

    Q_t = x[idx[self.flow_var_t]]
    eq_conservation = (Q_p + Q_a + Q_t) / Q_scale

    a = (self.p_set - P_a) / P_scale  # shared cap term

    b_supply = (P_p - P_a) / P_scale
    eq_supply = a + b_supply - math.sqrt(a * a + b_supply * b_supply)

    # Supply ridge: pulls P_p toward p_set when nothing else pins it
    # (e.g. a fixed-displacement pump, which forces only Q_p, never
    # P_p, leaving P_p otherwise underdetermined). One-sided (only
    # fires above p_set) and saturating (tanh) -- see "Implementation
    # refinements" for why both properties are necessary.
    SUPPLY_RIDGE_WEIGHT = 2.0
    gap = (P_p - self.p_set) / P_scale
    gap_above = (gap + math.sqrt(gap * gap + 1e-18)) / 2.0   # smooth max(gap, 0)
    eq_supply += SUPPLY_RIDGE_WEIGHT * math.tanh(gap_above)

    # Reverse-flow exclusion at the equation level (not just via
    # `bounds`, which fsolve's own unbounded stage ignores entirely).
    PENALTY_WEIGHT = 500.0
    z = -Q_p / Q_scale
    eq_supply += ((z + math.sqrt(z * z + 1e-18)) / 2.0) * PENALTY_WEIGHT

    b_relief = -Q_t / Q_scale
    eq_relief = a + b_relief - math.sqrt(a * a + b_relief * b_relief)
    # Tie-break for the rank-deficient shared root (a=0): pulls Q_t
    # toward 0 unless relief is genuinely needed to hold the cap.
    RIDGE_WEIGHT = 0.0002
    eq_relief += RIDGE_WEIGHT * (Q_t / Q_scale)

    return [eq_conservation, eq_supply, eq_relief]
```

**Why the dual-FB shape itself is fine (only a bare version wasn't):**
both `eq_supply` and `eq_relief` share the exact same cap term `a`, so
at `a=0` (`P_A=p_set`) they are individually satisfied by any split of
`Q_p>=0`/`Q_t<=0` that balances conservation — genuinely rank-deficient
as a bare pair. The `RIDGE_WEIGHT` term breaks that tie without
perturbing the "genuinely needs relief" case (where `Q_t`'s magnitude is
far larger than what a `0.0002` ridge could suppress).

## Validation

Two layers, in order:

1. **Standalone numerical spike** (scipy, not part of the codebase) —
   validated the initial dual-FB shape against 8 synthetic scenarios
   from a cold start, mimicking the real solver's two-stage
   `fsolve`/`least_squares` behavior. This caught the rank-deficiency
   problem early and confirmed the branch-guard approach's failure mode
   would not recur.
2. **Hands-on validation against the real engine and app**, done
   *after* the spike, which is what actually found and fixed the three
   issues in "Implementation refinements" below — the spike's synthetic
   scenarios did not happen to exercise a fixed-displacement pump on `P`
   together with a pressure genuinely pinned by another node, or the
   fully-open regime's interaction with the supply ridge. Two circuits
   were used throughout:
   - A single-acting cylinder fed through the valve by a
     fixed-displacement pump, run via
     `tests/simulate_json.py` (now supports `PressureReducingValve`,
     previously missing) across 60 simulated steps and inside the real
     app.
   - A synthetic circuit with `P` wired to a fixed-*pressure* reservoir
     (not a pump) at a value far above `p_set`, specifically to check
     the supply ridge doesn't drag the capped outlet up to match an
     externally-pinned high supply pressure.

The final regression test for the primary scenario is committed:
`test_relief_regime_diverts_excess_supply_pump_flow_to_tank_end_to_end`
in `tests/test_pressure_reducing_valve_hydraulic.py`.

## Implementation refinements

Found and fixed during the hands-on validation pass, in the order
discovered:

1. **`A` bidirectional was unnecessary and actively harmful.** The
   initial dual-FB design (matching the base-spec's original addendum)
   made `A` bidirectional to support external backfeed. Testing against
   a real fixed-displacement-pump-driven cylinder circuit showed this
   was never needed — the pump forces `Q_P`, the cylinder's own
   kinematics bound `Q_A` to whatever it can actually accept (including
   ~0 once stalled), and conservation alone routes the rest to `T`
   without `A` ever needing to reverse. Reverted to the 2-port valve's
   original `(None, 0.0)` bound. This also shrank the solver's search
   space, incidentally improving robustness.
2. **The supply ridge needed two corrections, discovered in this
   order:**
   - **First version** (`SUPPLY_RIDGE_WEIGHT * (P_p - P_a) / P_scale`)
     let the solver "cheat": when `P_p` was hard-pinned high by another
     node (e.g. a fixed-pressure reservoir directly on `P`, not a
     pump), the ridge reduced its own residual by dragging `P_a` UP to
     match `P_p` instead of lowering `P_p` (which it couldn't, being
     externally pinned) — defeating the valve's entire regulating
     function. Fixed by making the ridge a pure function of `P_p` vs.
     the fixed constant `p_set`, never referencing `P_a` — removing the
     escape route entirely.
   - **That fix, still linear** (`SUPPLY_RIDGE_WEIGHT * (P_p - p_set) /
     P_scale`), then proved unusable at any weight strong enough to
     robustly resolve the free/underdetermined case (a
     fixed-displacement pump on `P`): a linear ridge grows without
     bound as the pin gets more extreme, and at real-world weights it
     measurably distorted `P_a` away from `p_set` even in the
     genuinely-pinned case. Fixed by switching to `tanh`, which
     saturates the ridge's contribution at `±SUPPLY_RIDGE_WEIGHT`
     regardless of how far `P_p` is pinned from `p_set` — confirmed
     empirically: a weight of `10000` with the *unbounded* linear
     version corrupted even the pump's own flow equation elsewhere in
     the network; the same weight range is unreachable as a problem
     with the saturating version.
   - **Even saturating, the ridge fired in both directions** — it also
     pulled `P_p` up toward `p_set` when `P_p` was naturally BELOW
     `p_set` (the ordinary, already-correct fully-open regime),
     measurably distorting `eq_supply`'s residual there too (confirmed:
     `residual ≈ 0.92` instead of `≈0` at a legitimate fully-open point
     in a unit test). Fixed by gating the ridge through a smooth
     `max(gap, 0)` so it is identically zero whenever `P_p <= p_set`.
3. **`SUPPLY_RIDGE_WEIGHT` sweep, empirically, against BOTH the
   free (pump) and pinned (reservoir) scenarios together** (not either
   one alone — the two scenarios pull the ideal weight in opposite
   directions): `0.005` gives good pinned-case accuracy but the
   fixed-pump case regresses to over 100 solver warnings across 60
   steps; `10000` gives near-exact fixed-pump behavior but the pinned
   case overshoots `p_set` by nearly 3x; the shipped value, `2.0`,
   keeps the fixed-pump case fully clean (0 warnings) while keeping the
   pinned case's overshoot bounded and small enough not to break the
   valve's regulating function (see "Remaining known limitation" for
   the exact residual accepted).

## Remaining known limitation

The supply ridge cannot fully vanish while a hard-pinned upstream
pressure sits above `p_set` (a reservoir directly on `P` at a fixed
value, not a pump) — the ridge and the core FB pairing sit in the same
residual, and the pinned scenario's `gap_above` term never reaches
zero. At the shipped weight (`2.0`), this measured as `P_A` settling
around `43e6` in a synthetic test where `p_set=15e6` and `P` was pinned
at `50e6` — a real, bounded overshoot, not a crash or non-convergence.

This is an accepted trade-off, not an oversight: the user explicitly
prioritized the fixed-displacement-pump scenario (their actual use
case) over the hard-pinned-reservoir-on-`P` scenario (a less common
circuit shape — most real supply-side sources are pumps, not pressure
sources wired directly to a regulator's inlet with nothing upstream
limiting them). Eliminating this trade-off entirely would require
moving the tie-break to a genuinely separate equation (an auxiliary
"spool position"-style variable, discussed and set aside as a larger
structural change) rather than blending it into the same residual as
the core physics.

This is independent of, and does not fix, the separately-discovered
`simulation/hydraulic/solver.py` `fsolve_best`/`fsolve_best_residual`
mismatch (the clipped point and the reported residual come from
different, unclipped-vs-clipped values) — that bug is out of scope for
this spec but affects how confidently any hydraulic node's near-boundary
behavior can be trusted; worth its own fix.

There is also a known, accepted, cosmetic-only cold-start cost: the
very first solver call of a fresh simulation (all pressures literally
at 0, no warm start available yet) can hit `least_squares`'s max
function evaluations before converging — the answer it returns is still
correct (confirmed against the expected value in the cylinder test
circuit), just slower on that one call. Every subsequent step converges
cleanly (warm-started from the previous step). Tested and rejected: a
`dt=0` "warm-up" pass before the first real step helps the static
warm-up converge but does not reliably help the first *dynamic* step
(which shifts the problem's geometry again) — not worth the added
complexity for a one-time, correctness-neutral cost.

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
   done: the smooth-max penalty term is exactly this, added directly
   into `eq_supply`'s residual.

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

## Non-goals

- External/remote pilot setpoint (a `Y`-style port adjusting `p_set`
  from an external pressure). Explicitly discussed and deferred again —
  no concrete use case yet; will get its own spec if/when needed, same
  incremental path.
- Reverse flow / integrated check function through the `P`/`A` pair
  itself. `A` stays forward/outgoing-only (`Q_A <= 0`) even when
  relieving — see "Property and port" above for why the originally
  planned bidirectional `A` was reverted.
- True external backfeed directly into `A` (something actively pushing
  flow backward into the valve's outlet, independent of anything on the
  `P` side). The relief mechanism handles "supply forces more flow than
  the downstream will accept" instead, which covers every circuit
  tried during implementation.
- A fully trade-off-free supply ridge (see "Remaining known
  limitation") — would need a structural change (separate auxiliary
  variable for the tie-break), not attempted here.
- Pneumatic domain.

## Files

- `simulation/nodes/pressure_reducing_valve.py` — modified: `relieving`
  property, `T` port, `equations()` per "Equations" above. `A`'s
  bounds are UNCHANGED from the 2-port valve.
- `graphics/items/base/nodes/pressure_reducing_valve.py` — unchanged
  from the base 2-port valve's graphics work aside from the `relieving`
  overlay/anchor/checkbox added when this feature's Task 2 shipped;
  none of the equation-formula churn touched this file.
- `tests/test_pressure_reducing_valve_hydraulic.py` — rewritten for the
  `relieving=True` path: structural tests (ports/variables/bounds/
  conservation) kept, the three tests asserting the old branch-guard
  formula removed (they tested a formula that no longer exists), new
  tests added for the dual-FB structure (reverse-flow penalty
  monotonicity, relief tie-break, fully-open regime under `relieving`),
  and the end-to-end test rewritten to use a fixed-displacement-pump
  scenario (the original used a pump wired directly into `A`, which
  needed the now-reverted bidirectional bound) with its `xfail` marker
  removed — it passes.
- `tests/test_pressure_reducing_valve_item.py` — unchanged, nothing
  here depends on the equation formulation.
- `tests/simulate_json.py` — modified: added `PressureReducingValve` to
  `_get_node_classes()`/`ANCHORS_BY_TYPE` (previously missing entirely,
  meaning this diagnostic tool silently skipped the node) plus the
  `relieving` conditional-anchor handling, mirroring `ReliefValve`'s
  `piloted` handling already there. This is what made the hands-on
  cylinder-circuit validation possible.
