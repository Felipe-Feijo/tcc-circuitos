# Pressure reducing valve — relief port (3-way variant) — design

Date: 2026-09-03
Status: implemented, but NOT functional — see "Known limitation / status"
below. Do not build on this spec's relief mechanism until a follow-up
spec addresses the three points listed there.

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
in "Known limitation / status".

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

Extends the existing branch (unchanged in the `relieving=False` path —
byte-identical to what already shipped):

```python
if self.relieving:
    Q_t = x[idx[self.flow_var_t]]
    eq_conservation = (Q_p + Q_a + Q_t) / Q_scale
else:
    eq_conservation = (Q_p + Q_a) / Q_scale

if P_a > self.p_set and Q_p <= 0:
    eq_supply = Q_p / Q_scale                      # unchanged: supply stays shut
    if self.relieving:
        eq_relief = (P_a - self.p_set) / P_scale   # NEW: pulls P_A back to p_set via T
else:
    a = (self.p_set - P_a) / P_scale
    b = (P_p - P_a) / P_scale
    eq_supply = a + b - sqrt(a*a + b*b)             # unchanged
    if self.relieving:
        eq_relief = Q_t / Q_scale                  # dead port here -- no relief needed

if self.relieving:
    return [eq_conservation, eq_supply, eq_relief]
return [eq_conservation, eq_supply]
```

Rejected alternative: pairing `(P_A - p_set)` against `Q_T` as a second,
independent Fischer-Burmeister complementarity (mirroring the existing
supply-side FB). Rejected because both FB pairs would be satisfied by the
same condition (`P_A = p_set`) without anything to decide *which* port
(`P` throttling or `T` bleeding) supplies the correction — the system
would be rank-deficient exactly at the most commonly visited state.
Branching on the trial iterate (same technique this file's existing
closed-regime branch already uses, and the same technique
`ReliefValve.equations()`'s own passive-regime branch uses) sidesteps
this: the branch condition decides the regime, and each branch's
equations are then simple, well-posed equalities.

Conservation becomes 3-port when `relieving=True`:
`Q_P + Q_A + Q_T = 0` (was `Q_P + Q_A = 0`).

`variables`, `hydraulic_ports`, `bounds` all conditionally include the
`T` entries only when `relieving=True` — same conditional-inclusion
pattern `ReliefValve` already uses for `piloted`'s `Y`.

## Known limitation / status

**The relief mechanism as designed does not converge in the real solver
and cannot currently be relied upon.** Discovered in the implementation
plan's final whole-branch review, confirmed and root-caused by an
independent re-review (both reports live under
`.superpowers/sdd/2026-09-03-pressure-reducing-valve-relief-port/`).
A `relieving=True` valve, wired to a real circuit (`SimulationEngine`,
not `equations()` called in isolation), fails to hold `P_A` at `p_set`.
Regression-pinned by
`tests/test_pressure_reducing_valve_hydraulic.py::test_relief_regime_holds_outlet_at_p_set_end_to_end`,
marked `xfail(strict=True)` rather than left red or deleted.

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

**A follow-up spec needs to address all three, not just one:**

1. Replace the hard branch guard with a smooth relief-orifice
   formulation (e.g. `Q_T = -k · smooth_max(0, P_A - p_set)`) so the
   steady state sits strictly inside the branch's domain instead of on
   its boundary, and the residual is differentiable everywhere.
2. Decouple that formulation from `Q_P`'s active bound — the corner
   described above exists independently of the branch's exact shape as
   long as the relief condition and a hard `Q_P` bound share a boundary.
3. Exclude the reverse-flow root (`Q_P < 0`) with an *equation*, not
   just a `bounds` entry — `fsolve`'s own unbounded stage will keep
   converging onto it regardless of what `bounds` says, the same way
   `CheckValve` excludes its own disallowed direction via a
   complementarity pair rather than relying on bounds alone.

The `solver.py` clip/residual mismatch is a separate, pre-existing
defect independent of this feature (any node encoding physics in
`bounds` rather than `equations()` is exposed to it) — worth its own
fix, but out of scope for this spec.

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
  itself. Still out of scope — `T` provides a distinct, separate relief
  path; it does not reopen `A→P` reverse flow.
- Pneumatic domain.

## Files

- `simulation/nodes/pressure_reducing_valve.py` — modified (add
  `relieving` property, `T` port, extend `equations()`/`variables`/
  `hydraulic_ports`/`bounds`)
- `graphics/items/base/nodes/pressure_reducing_valve.py` — modified (add
  `relieving` overlay/anchor toggle, dialog checkbox)
- `tests/test_pressure_reducing_valve_hydraulic.py` — modified, new
  tests for the `relieving=True` path (3-port conservation, relief
  regime is an exact root, `relieving=False` path unchanged/regression)
- `tests/test_pressure_reducing_valve_item.py` — modified, new tests for
  the `T` anchor toggle (mirrors `ReliefValve`'s piloted-toggle tests)
