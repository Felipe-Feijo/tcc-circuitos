# Internal leakage defect for hydraulic cylinders — design

Date: 2026-10-04
Status: draft, pending review

## Context

The `DefectMixin` framework (see `2026-09-28-defect-mixin-design.md`)
covers every hydraulic parameter that can be defected by a plain value
swap: `k` on directional/throttle valves, `p_set` on relief/pressure
reducing valves, `P0` on the accumulator, `Q`/`Q_max`/`H_shutoff` on
the pumps. The next quantitative hydraulic defect is internal leakage,
which needs new physics: no leakage path exists in any equation today.

This cycle covers leakage across the piston of both hydraulic
cylinders. Directional valve (spool) leakage is out of scope: it would
rewrite the equations of all five valves and gets its own design.

## Goal

`set_defect {"leak": c}` on a hydraulic `DoubleActingCylinder` or
`SingleActingCylinder` adds a laminar leakage path with coefficient
`c` (m³/s/Pa); `clear_defect` removes it. With `c = 0` the equations
are algebraically identical to today's, so healthy circuits are
unaffected.

## Physics

Project convention: Q > 0 means fluid entering the component at that
port; pressures are gauge.

### Double-acting: leakage A → B across the piston

```
Q_L = c_leak · (P_A − P_B)
v   = (Q_A − Q_L) / A_A          # piston velocity
Q_B = −(A_B · v + Q_L)           # conservation equation
```

- Force balance is unchanged; the friction term uses this `v`.
- End-stop complementarity uses `q = A_A · v / Q_scale` instead of
  `Q_A / Q_scale`: at a stop the piston halts but `Q_A = Q_L` keeps
  flowing.
- With `c_leak = 0`, the conservation equation reduces to today's
  `(A_B/A_A)·Q_A + Q_B = 0`.

### Single-acting: leakage A → vented spring chamber (P = 0)

```
Q_L = c_leak · P_A
v   = (Q − Q_L) / A
```

- Force, contact force and complementarity equations use this `v`
  instead of `Q / A`.
- The retracted-stop branch that forces `Q → 0` forces `v → 0`
  instead.
- `bounds`: the extended-stop bound `Q ≤ 0` is infeasible with leakage
  (a pump holding pressure gives `Q = c·P > 0`), so it is dropped when
  `c_leak > 0`; the equation-level complementarity (now on `v`) still
  holds the stop. The retracted-stop bound `Q ≥ 0` stays valid since
  `Q_L ≥ 0`.

### Expected symptoms

- Double-acting, fixed-displacement pump on A, B to tank: extension
  speed drops from `Q/A_A` to `(Q − Q_L)/A_A`.
- Single-acting with port A blocked under spring/load: the piston
  sinks at `v = −c·P_A/A`.
- Double-acting with A blocked and B to tank, under load: drifts.
  With both ports blocked it does not drift (incompressible fluid,
  unequal areas) — physically correct.

## Code structure

### Simulation (`simulation/nodes/cylinder/`)

- Both classes become `class X(DefectMixin, Node, HydraulicMixin)` with
  `DEFECT_FIELDS = {"leak": "c_leak"}`; `self.c_leak = 0.0` is set in
  the `__init__` hydraulic block. In pneumatic the attribute doesn't
  exist and the mixin skips the key.
- `_on_defect_changed` clamps `c_leak` to `max(0.0, c_leak)`.
- A private helper computes `v` from (Q, pressures):
  `_piston_velocity(Q_A, P_A, P_B)` (double) / `_piston_velocity(Q, P_A)`
  (single). `equations` uses it with solver-vector values.
- A public `piston_velocity` property reads the anchors after the solve
  (returns `None` when flow/pressure is an error string) and calls the
  same helper. It is the single source for position integration
  (`_integrate_hydraulic` / `post_step_update`), for the double-acting
  `locked_fwd`/`locked_bwd` release (on the sign of `v`), and for the
  graphics velocity label.
- `initial_guess` at the end stops guesses `Q_A = Q_L` (and
  `Q_B = −Q_L` for double-acting) from the anchors' pressures instead
  of 0.

### Graphics

- `CylinderItem.defect_fields()` (shared by both cylinders), hydraulic
  only, one number field: key `"leak"`, label
  `"Internal leakage c_L (m³/s/Pa)"`, placeholder
  `"ex: 1e-12  (≈ 0.6 L/min @ 100 bar)"`, `min_value=None` (healthy is
  0 and `min_value` is exclusive; negatives are clamped by the node).
  Uses `QCoreApplication.translate("CylinderItem", ...)`, not `self.tr`
  (inherited-method context gotcha, see
  `scripts/compile_translations.py`).
- `CylinderItem._update_velocity_from_domain` reads
  `domain_node.piston_velocity` instead of `anchor.flow / area`.

### Translations

New `<message>` under the `CylinderItem` context in both `.ts` files
(pt_BR: `"Vazamento interno c_L (m³/s/Pa)"`), `.qm` recompiled with
`scripts/compile_translations.py` (needs `../venv/Scripts` on PATH).

## Testing

New `tests/test_double_acting_cylinder_leak_defect.py` and
`tests/test_single_acting_cylinder_leak_defect.py`, following the
existing `tests/test_*_defect.py` files:

- Mixin: fresh node has no defect; set changes `c_leak` and marks
  active; clear restores 0; negative value clamps to 0.
- Regression: with `c_leak = 0`, the existing cylinder test suites pass
  unchanged (they are the guard for "algebraically identical").
- Double-acting integration (`SimulationEngine`): fixed pump → A, B →
  reservoir; with leak, `piston_velocity` ≈ `(Q − c·(P_A − P_B))/A_A`
  and position advances more slowly over the same steps than healthy;
  at the extended stop with a relief valve, `Q_A ≈ Q_L > 0` while
  `x` stays at stroke.
- Single-acting integration: cylinder extended under spring with A
  blocked (closed 2/2 valve or equivalent dead end); with leak, `x`
  decreases step by step with `v ≈ −c·P_A/A`; healthy stays put.
- Graphics: `defect_fields()` returns one `"leak"` spec in hydraulic,
  none in pneumatic; dialog prefilled from the live node; apply emits
  `{"action": "set_defect", "leak": <float>}`; pt_BR label; velocity
  label uses `piston_velocity`.

## Out of scope

- Directional valve (spool) leakage.
- Check valve cracking pressure / leakage.
- External leakage to the environment for the double-acting cylinder.
