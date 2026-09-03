# Pressure reducing valve — design

Date: 2026-09-03
Status: approved for implementation plan

## Context and problem

New hydraulic component: single-stage, direct-acting pressure reducing
valve ("válvula redutora de pressão"). Reduces a downstream branch's
pressure to a fixed setpoint regardless of the upstream (supply)
pressure, by throttling its own main orifice — normally open, no tank
port. Follows the same one-node-type-per-spec pattern already used for
`check_valve`, `accumulator` and `relief_valve`.

Conceptually the mirror image of `ReliefValve`
(`simulation/nodes/relief_valve.py`): relief is normally *closed* and
opens to a tank port when the *upstream* pressure exceeds its setpoint;
this valve is normally *open* and throttles its own passage when the
*downstream* pressure would exceed its setpoint. No tank port exists in
this single-stage version — see Non-goals.

## Ports and properties

Two ports only: `P` (inlet, supply side) and `A` (outlet, regulated
side). Named to match the `P`/`A`/`B`/`T` convention already used by the
directional valves — `T` is avoided since there is no tank connection.

One required property: `p_set` (Pa), same shape as `ReliefValve.p_set`.

## Equations (hydraulic domain)

Same complementarity technique already used by `ReliefValve` and
`CheckValve` (Fischer-Burmeister smoothing), sensing the *outlet*
pressure instead of the inlet:

```
Q_P + Q_A = 0                              # conservation

a = (p_set - P_A) / P_scale                # wants a >= 0: P_A never exceeds setpoint
b = (P_P - P_A) / P_scale                  # wants b >= 0: valve only drops pressure, never boosts it
eq_fb = a + b - sqrt(a*a + b*b)            # == 0  =>  a>=0, b>=0, a*b=0
```

Two regimes, selected implicitly by the solver via `eq_fb`:

- **Fully open** (`b=0`): `P_A = P_P`, no pressure drop. Valid as long as
  this doesn't push `P_A` above `p_set` (`a >= 0` holds).
- **Regulating** (`a=0`): `P_A` held at `p_set`, with `P_P >= P_A` (the
  valve throttles down to hold the setpoint).

A third regime, handled outside the FB pairing above: **closed**
(`P_A > p_set` and `Q_P <= 0`). This is a state the 2-term FB pairing
has no root for — `a` stays negative regardless of `b` whenever `P_A`
exceeds `p_set` — but it's physically real: something outside the
valve's control (a blocked downstream branch, or a stale `p_previous`
seed right after a topology change) has pushed the outlet above
setpoint while there's no forward flow trying to happen. `equations()`
detects this from the trial values and substitutes `Q_P = 0` directly,
so the valve holds shut instead of faulting the solve.

`bounds`: `Q_P >= 0`, `Q_A <= 0` — forward flow only, no reverse/check
function in this version (see Non-goals).

`p_hint = p_set` (mirrors `ReliefValve.p_hint`).

`get_visual_state()`: `"regulating"` when `P_P` is measurably above
`P_A` (throttling), `"open"` otherwise. Cosmetic only, doesn't feed back
into the equations.

## Graphics item

Sprite: `resources/nodes/pressure_reducing_valve/pressure_reducing_valve.png`,
200×162px (already created), white-on-transparent, ISO symbol matching
the slide's "simples estágio" schematic — vertical flow line entering at
the top, control box with feedback dashed line, spring on the right.

Anchors, measured directly from the sprite's opaque pixels (flow line
spans x=97..100 at both y=0 and y=161, center 98.5):

| Anchor | Position                    | Exit direction |
|--------|------------------------------|-----------------|
| P      | `(width*98.5/200, 0)`        | top             |
| A      | `(width*98.5/200, height)`   | bottom          |

Both anchors always present — no conditional anchors, no properties
besides `p_set`, so no `apply_properties`-driven anchor churn like
`ReliefValve`'s pilot port.

`node_type = "pressure_reducing_valve"`, `simulation_cls` pointing at
the node below. `palette_meta()`: `domains=("hydraulic",)`, name
"Pressure Reducing Valve". Registration is automatic via
`node_registry.py` — no central file to edit.

Properties dialog: single required number field for `p_set` (Pa), same
`add_number_field(..., required=True)` pattern as `ReliefValve`'s
cracking-pressure field, no boolean/pilot field.

## Non-goals

- **Relieving/3-port variant** (`A→T` bleed when downstream pressure
  rises from an external cause after the `P→A` path is already fully
  closed). Real 3-way "reducing-and-relieving" valves need this, but it
  couples two orifices to one shared spool position, which is
  meaningfully more equation work than a dead sensing-only port (unlike
  `ReliefValve`'s `piloted` `Y`, which carries no real flow). Deferred to
  a follow-up spec, same incremental path `ReliefValve` took
  (`2026-08-10-relief-valve-external-pilot-design.md` came after the
  base direct-acting version).
- **Reverse flow / integrated check function.** Some real reducing
  valves allow free reverse flow when the downstream side is
  over-pressurized by something external. Not modeled here — `bounds`
  keep `Q_P >= 0` unconditionally.
- **External/remote pilot setpoint** (a `Y`-style port like
  `ReliefValve.piloted`, adjusting `p_set` from an external pressure
  instead of the internal spring). Not requested for this component.
- **Pneumatic domain.** Hydraulic only, like `ReliefValve` and
  `Accumulator`.

## Files

- `simulation/nodes/pressure_reducing_valve.py` — new
- `graphics/items/base/nodes/pressure_reducing_valve.py` — new
- `tests/test_pressure_reducing_valve_hydraulic.py` — new, mirrors
  `test_relief_valve_hydraulic.py`: fully-open regime, regulating
  regime, conservation, bounds.
- `tests/test_pressure_reducing_valve_item.py` — new, mirrors
  `test_relief_valve_item.py`: anchors, palette registration,
  properties dialog required-field validation.
