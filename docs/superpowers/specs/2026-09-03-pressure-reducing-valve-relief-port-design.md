# Pressure reducing valve — relief port (3-way variant) — design

Date: 2026-09-03
Status: approved for implementation plan

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
