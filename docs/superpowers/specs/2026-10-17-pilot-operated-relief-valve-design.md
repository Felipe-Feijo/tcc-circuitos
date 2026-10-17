# Pilot-operated relief valve (vent port X) — design

Date: 2026-10-17
Status: design approved in discussion; not yet implemented.

## Context and problem

`ReliefValve` (`simulation/nodes/relief_valve.py`) is direct-acting and
quasi-static: closed, or regulating at exactly `p_set`, with no ΔP–Q
characteristic. A pilot-operated (two-stage) relief valve modeled the
same way would be indistinguishable from it — the real-world advantage
of a pilot-operated valve (a flat ΔP–Q curve) is already "perfect" in
the direct-acting model.

What *does* distinguish it in this simulator is the **vent / remote
control port X**: draining the pilot chamber through X makes the valve
open **below** its own setting. That enables the two classic circuits
this component exists for:

- **pump unloading (venting):** X to tank (usually through a 2/2 valve)
  → system pressure drops to the main-stage spring pressure;
- **remote pressure control:** X to a small remote relief → system
  pressure follows the remote setting.

`ReliefValve`'s optional `Y` port cannot do this: it is sensing-only
(`Q_Y = 0`) and raises the threshold (`p_set + P_Y`); it can never lower
it. `ReliefValve` is not changed by this spec.

Reference: HAWE data sheet D 4350 (types DV/DVE/DF), section 6.3
"Circuit examples" shows exactly the circuits tested below (X free,
X → 2/2 to tank for pump idling, X → remote pilot valve).

## Terminology

"Pilot" is overloaded in this codebase, so this spec uses:

- **pilot stage** — the small internal direct-acting relief (cone +
  adjustable spring) that limits the chamber pressure;
- **chamber** — the volume between the orifice, the main poppet's spring
  side and the pilot stage; its pressure is `P_X`;
- **port X** — external access to the chamber ("remote control / vent").
  Not called "pilot" anywhere user-facing.

User-facing name: "Relief Valve (pilot-operated)" / "Válvula de Alívio
(pré-operada)", pairing with the existing "Relief Valve (direct)" /
"Válvula de Alívio (direta)".

## Physical model

Three elements, all quasi-static:

1. **Orifice P → chamber** (fixed restriction, "gicleur"): turbulent
   orifice, same form as `ThrottleValve`.
2. **Pilot stage, chamber → T**: Fischer–Burmeister complementarity,
   threshold `p_set` on `P_X`.
3. **Main stage, P → T**: Fischer–Burmeister complementarity, threshold
   `P_X + p_vent` on `P_P` (`p_vent` = weak main-poppet spring).

Pilot flow through the orifice either leaves through the pilot stage or
through port X. Steady-state system pressure:

    P_P = min(p_set, P_remote) + p_vent

| X connected to | regulates at |
|---|---|
| nothing (plugged) | `p_set + p_vent` |
| tank | `p_vent` |
| remote relief, `p_r < p_set` | `p_r + p_vent` |
| remote relief, `p_r ≥ p_set` | `p_set + p_vent` |

### Setpoint convention (decided)

`p_set` is the **pilot spring setting**, literally — not the system
pressure. With X free the gauge reads `p_set + p_vent`. This was chosen
over "p_set = system pressure, pilot at p_set − p_vent" because both
springs are user-editable: each field maps to one physical spring, and
the system pressure is their sum, matching the cutaway students learn.
The dialog labels make this explicit (see Graphics).

Consequence: a pilot-operated valve with `p_set = 100 bar` behaves like
a direct-acting `ReliefValve` with `p_set = 100 bar + p_vent` while X is
free — not like one with `p_set = 100 bar`.

## Domain node — `simulation/nodes/pilot_operated_relief_valve.py`

`PilotOperatedReliefValve(DefectMixin, Node, HydraulicMixin)`,
`node_type = "pilot_operated_relief_valve"`,
`DEFECT_FIELDS = {"p_set": "p_set"}` (misadjusted pilot spring).

### Properties

| property | required | default | meaning |
|---|---|---|---|
| `p_set` | yes | — | pilot spring setting (Pa); `ValueError` if missing |
| `p_vent` | no | `3e5` | main-poppet spring (Pa) |

Validation: `p_set > 0`, `p_vent > 0` (`ValueError` otherwise).
Orifice conductance `k = 3e-8 m³/s/√Pa` is a class constant, not a
property: it only sets the pilot flow (≈ 1 L/min at 3 bar), never a
regulated pressure.

### Ports and variables

All three ports are real flow ports in `hydraulic_ports()`:
`{"P": Q_P, "T": Q_T, "X": Q_X}`. **No `dead_ports()`**: an unconnected X
must not be a validation error.

Unconnected X needs no special handling and no engine change:
`SimulationEngine._assign_pressure_vars()` gives every hydraulic anchor
a pressure variable (a lone anchor forms its own group), and
`_try_solve()` builds a `NodeContinuity` for every group listed in
`hydraulic_ports()`. A lone X therefore gets `Q_X = 0` — exactly a
plugged port. The same mechanism is documented for the PRV's
unconnected `T`.

Own variables (sign convention as `ReliefValve`: positive = into the
component):

| variable | bounds | meaning |
|---|---|---|
| `Q_{id}_P` | `(0, None)` | inlet |
| `Q_{id}_T` | `(None, 0)` | outlet |
| `Q_{id}_X` | free | port X (negative = pilot flow leaving through X) |
| `Q_{id}_main` | `(0, None)` | main stage P → T |
| `Q_{id}_pilot` | `(0, None)` | pilot stage chamber → T |

plus the P, T, X anchor pressure variables, collected the same way
`ReliefValve.variables` does.

### Equations (5, matching the 5 own flow variables)

With `Q_orif = Q_P − Q_main` (flow through the orifice):

1. T balance: `(Q_T + Q_main + Q_pilot) / Q_ref = 0`
2. chamber balance: `(Q_orif − Q_pilot + Q_X) / Q_ref = 0`
3. orifice: `((P_P − P_X) − copysign((Q_orif / k)², Q_orif)) / P_ref = 0`
4. pilot stage FB: `a = (p_set − P_X) / P_ref`, `b = Q_pilot / Q_ref`
5. main stage FB: `a = (P_X + p_vent − P_P) / P_ref`, `b = Q_main / Q_ref`

Both FB residuals use `a + b − sqrt(a² + b²)` and reproduce
`ReliefValve.equations()`' passive-regime guard (outlet backpressured
above the threshold → `eq = (P_in − P_out) / P_ref`), with "in" being
`P_X` / `P_P` and "out" `P_T`, so the node stays equivalent to the
discrete build below in every regime. The guard is duplicated, not
imported: `ReliefValve` is not touched.

`p_hint = p_set + p_vent`. `set_scale` as `ReliefValve`
(`p_ref ≥ 1e5`, `q_ref ≥ 1e-10`). `initial_guess`: flows 0, P pressure
from the anchor hint as `ReliefValve`. `update()` no-op (no state).

### Why own equations instead of composing existing nodes

The discrete build (below) proves the equation system, but delegating to
three internal node instances would require keeping their anchors'
`pressure_var`s in sync with the engine's assignment on every update,
and forwarding bounds/scale/guess/results — fragile for no gain. The
discrete build is used as the **test oracle** instead.

## Numerical validation (done)

Throwaway spike, real `SimulationEngine`, fixed-displacement pump
`Q = 1e-3 m³/s`, monitor's discrete build: `ThrottleValve(k=3e-8)`
P → chamber, `ReliefValve(piloted, p_set=p_vent=3e5)` as main stage with
`Y` on the chamber, `ReliefValve(p_set=1e7)` chamber → tank.

| case | P_P (bar) | expected | P_X (bar) |
|---|---|---|---|
| X free | 103.000 | 103 | 100 |
| X → tank | 3.000 | 3 | 0 |
| remote relief 50 bar | 53.000 | 53 | 50 |
| remote relief 150 bar | 103.000 | 103 | 100 |

All converged to the exact values; pilot flow 1.64e-5 m³/s. Only the
50-bar remote case needed one `least_squares` fallback round before
`fsolve` converged. No ridge/penalty terms (as in the PRV) were needed.

## Graphics — `graphics/items/base/nodes/pilot_operated_relief_valve.py`

`PilotOperatedReliefValve(NodeItem)`, `node_type =
"pilot_operated_relief_valve"`, `simulation_cls` = the domain node,
discovered by the node registry through `palette_meta()` (no registry
change). Domain: hydraulic only.

### Sprites (done)

`resources/nodes/pilot_operated_relief_valve/`, 254 × 161, white on
transparent; sources in `resources/gimp_files/`:

- `pilot_operated_relief_valve.png` — body (professor's symbol: main
  stage with internal pilot from P, orifice on the P → chamber pilot
  line, ISO indirect-actuation block with the triangle pointing away
  = actuation by pressure release, spring without adjust arrow like
  `relief_valve.png`), X line open at the right edge;
- `pilot_operated_relief_valve_x_plug.png` — only the plug bar at the end
  of the X line.

### Anchors (measured on the PNGs)

| anchor | position | exit |
|---|---|---|
| P | `(width * 98.5/254, 0)` | top |
| T | `(width * 98.5/254, height)` | bottom |
| X | `(width, height * 19.5/161)` | right |

P/T: opaque pixels on the top/bottom rows at x = 97–100. X: the last
dash touches the right edge at y = 17–22. Documented in the module
docstring as `relief_valve.py` does.

### Automatic plug overlay

`paint()` draws the plug overlay when
`self.anchors["X"].connection_count() == 0`, so the drawing always
matches what the solver does (unconnected X ≡ plugged). No property.

Repaint on connect/disconnect: X uses a small `AnchorItem` subclass
defined in the component's own file, overriding `refresh_junction_dot()`
to call `super()` and then `self.node.update()`. `refresh_junction_dot()`
is already called by `GraphicsView.create_connection`,
`GraphicsView.split_connection_at` and `ConnectionItem.prepare_delete`.
Paths that may not call it (connection merge in
`connection_item.py`, JSON load, undo/redo) at worst leave the overlay
stale until the next repaint — cosmetic only; `paint()` always reads
the live count. Covered by an item test.

### Dialog and defect

- Palette name: `QCoreApplication.translate("PilotOperatedReliefValve",
  "Relief Valve (pilot-operated)")`.
- Dialog title: "Pilot-Operated Relief Valve — Properties".
- Fields: "Pilot setting p_set (Pa)" (required) and "Main-stage spring
  p_vent (Pa)" (optional, placeholder shows the 3e5 default; empty →
  property removed so the domain default applies).
- `defect_fields()`: `p_set`, same spec shape as `ReliefValve`.
- Persistence: properties dict, same path as other nodes; a saved file
  without `p_vent` loads with the default.

### i18n

All new strings through `tr()` / `QCoreApplication.translate` with the
`PilotOperatedReliefValve` context; regenerate the catalogs per the
project's i18n workflow (pylupdate6, then add pt_BR translations, never
`--no-obsolete`), and recompile `circuiteditor_pt_BR.qm`.

## Testing

Domain unit tests (`tests/test_pilot_operated_relief_valve_hydraulic.py`):

- node_type, ports, variables, bounds; X not in `dead_ports`;
- missing/invalid `p_set`, invalid `p_vent` → `ValueError`; `p_vent`
  default applied;
- exact roots per regime: closed (all flows 0, `P_X = P_P`), pilot-only,
  regulating (`P_X = p_set`, `P_P = p_set + p_vent`), vented
  (`P_X = 0`, `P_P = p_vent`);
- unconnected X builds and validates through `GraphBuilder` without
  errors.

End-to-end (real `SimulationEngine`, fixed-displacement pump, tank
reservoirs):

1. X free → `P_P ≈ p_set + p_vent`, and equal to the discrete build and
   to a direct `ReliefValve(p_set + p_vent)` in the same circuit;
2. X → tank → `P_P ≈ p_vent`;
3. X → remote `ReliefValve(p_r < p_set)` → `P_P ≈ p_r + p_vent`;
4. X → remote `ReliefValve(p_r > p_set)` → `P_P ≈ p_set + p_vent`;
5. X → 2/2 valve → tank, switched open and closed mid-simulation →
   `P_P` drops to ≈ `p_vent`, returns to ≈ `p_set + p_vent`;
6. `p_set` defect applied and cleared mid-simulation → regulated
   pressure follows `p_set_defect + p_vent`, then returns.

Defect test (`tests/test_pilot_operated_relief_valve_defect.py`)
following `test_relief_valve_defect.py`.

Graphics item test (`tests/test_pilot_operated_relief_valve_item.py`):
anchor positions/exits, palette meta, dialog round-trip (with and
without `p_vent`), plug overlay shown when X is unconnected and hidden
after connecting / shown again after deleting the connection, JSON
save/load round-trip.

`tests/simulate_json.py`: register the type and its anchors
(`["P", "T", "X"]`).

Finish: full suite green; `git status` shows changes only in the new
component's files, its tests, sprites, i18n catalogs and
`tests/simulate_json.py`.

## Non-goals

- external pilot supply and external pilot drain variants;
- `p_vent` as a defect field (possible follow-up: "broken main spring");
- ΔP–Q characteristic / pressure override;
- orifice `k` as a user property;
- any change to `simulation_engine.py`, `simulation/hydraulic/`, the node
  registry, `ReliefValve` or other core files. If implementation finds
  one unavoidable, stop and raise it before editing.
