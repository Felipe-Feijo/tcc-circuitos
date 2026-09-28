# Generic defect framework (DefectMixin) — design

Date: 2026-09-28
Status: approved for implementation plan

## Context and problem

"Simulate defect..." (injecting a fault into a component during a
running simulation, for demonstration and for the report's defect
markers) exists today only for the five hydraulic directional valves
(2/2, 3/2, 4/2, 4/3, 5/2). Two defects are supported: a changed
conductance `k` (partial clogging) and a stuck spool.

The UI side is already generic: `NodeItem.build_defect_dialog()` /
`apply_defect_from_dialog()` are opt-in hooks, the context menu shows
"Simulate defect..." for any item that returns a dialog, the defect
indicator reads `domain_node.defect_active`, and `FrameRecorder`
records a `DefectEvent` for any node exposing `defect_active`.

The domain side is not generic. Everything lives in `DirectionalValve`
(`simulation/nodes/directional_valve/directional_valve.py`):
`_apply_defect_command`, `_clear_defect`, `defect_active`,
`_stuck_defect`, `_defect_note`, plus `_k_default` captured by
`_init_hydraulic_k`. Restoring the original value is hand-written per
parameter — forgetting that capture already broke `defect_active` /
`_clear_defect` silently on three of the five valves once. The item
side is likewise hand-written (~60 lines in `DirectionalValveItem`,
reaching into ad-hoc `dialog._field_k` / `_field_stuck` /
`_field_note` attributes).

Adding more defects (planned: pumps, relief valves, contacts, coils,
cylinder sensors, check valves...) on top of this would copy that
pattern per component.

## Goal

A generic defect mechanism, domain and UI, such that adding a new
defect to a component means declaring it — not reimplementing
apply/restore/detect/dialog plumbing.

Validated by migrating the existing directional-valve defects onto it
with **no behavior change**.

## Non-goals

- No new defects. Pneumatic directional valves keep no defect menu
  (even though `stuck` would work there) — deferred, as are all the
  other components listed above.
- Defects stay out of `get_state()`/`set_state()`: stepping backward in
  history does not undo a defect (unchanged).
- Defects stay non-persistent: they live only in the running
  simulation's domain instances (unchanged).
- No hidden-defect / diagnosis-exercise mode.

## Domain: `DefectMixin`

New file `simulation/nodes/defect.py`. Nodes inherit it ahead of
`Node` so it intercepts defect commands first:

```python
class DirectionalValve(DefectMixin, Node):
    DEFECT_FIELDS = {"k": "k", "stuck": "stuck_defect"}
```

`DEFECT_FIELDS` maps a command key to an instance attribute name. The
node initializes each attribute to its healthy value in `__init__` and
its own logic reads the attribute as usual — the mixin knows nothing
about physics. Any attribute type works: a physical float (`k`), a mode
bool (`stuck_defect`), an enum string, an int.

Adding a defect to a node = (1) an attribute with a healthy default,
(2) node logic reading it, (3) one `DEFECT_FIELDS` entry.

### Behavior

- `handle_defect_command(cmd) -> bool`:
  - `action == "set_defect"` → `_set_defect(cmd)`, return True.
  - `action == "clear_defect"` → `_clear_defect(cmd)`, return True.
  - anything else → False.
- `handle_command(cmd)`: `if not self.handle_defect_command(cmd):
  super().handle_command(cmd)`. A subclass that overrides
  `handle_command` (e.g. `DirectionalValve`, which precedes the mixin in
  the MRO) must start with
  `if self.handle_defect_command(command): return`.
- `_set_defect(cmd)`: for each key in `cmd` that is in `DEFECT_FIELDS`
  and whose attribute exists on the instance (`hasattr`):
  - snapshot the attribute's current value into `_defect_originals`
    the first time that attribute is touched (never overwritten while
    the snapshot is held);
  - assign the new value coerced to the original's type
    (`type(original)(value)`; bool originals use `bool(value)`).

  Keys absent from the command are left as-is. Keys not in
  `DEFECT_FIELDS`, and attributes the instance doesn't have (e.g. `k`
  on a pneumatic valve), are silently ignored. Then sets
  `defect_note = cmd.get("note", "")` and calls `_on_defect_changed()`.
- `_clear_defect(cmd)`: restores every snapshotted attribute, empties
  the snapshot, sets `defect_note = cmd.get("note", "")`, calls
  `_on_defect_changed()`.
- `defect_active` (property): `any(getattr(self, attr) != original for
  attr, original in _defect_originals.items())`. Setting a field back
  to its original value by hand therefore reads as inactive.
- `defect_value(key)`: current value of the attribute mapped by `key`,
  or `None` if unmapped/absent. Used by the UI to prefill the dialog
  without knowing attribute names.
- `defect_note: str` — free-text note of the last set/clear command
  (replaces `_defect_note`). `FrameRecorder._capture_defect_events`
  reads `defect_note` instead of `_defect_note`.
- `_on_defect_changed()` — optional hook for nodes that need to
  recompute derived values after set/clear. Default: no-op.

State (`_defect_originals = {}`, `defect_note = ""`) is initialized in
a cooperative `DefectMixin.__init__(self, *args, **kwargs)` that calls
`super().__init__(*args, **kwargs)` first. Since the mixin precedes
`Node` in the MRO, the subclass's existing `super().__init__(...)` call
reaches it unchanged — no subclass has to remember to call anything.

### Directional valve migration

- `DirectionalValve` uses the mixin with
  `DEFECT_FIELDS = {"k": "k", "stuck": "stuck_defect"}`.
- `_stuck_defect` is renamed `stuck_defect` (read by
  `_compute_body_state`).
- Removed: `_apply_defect_command`, `_clear_defect`, the hand-written
  `defect_active`, `_defect_note`, `_k_default`.
- `_init_hydraulic_k` keeps only validation + `self.k = float(k)`; its
  docstring drops the `_k_default` rationale (the mixin makes it moot).
- Command format is unchanged:
  `{"action": "set_defect", "k": float, "stuck": bool, "note"?: str}`,
  `{"action": "clear_defect", "note"?: str}`.

## UI: declarative defect dialog

### `DefectFieldSpec`

In `graphics/utils/defect_dialog.py`:

```python
@dataclass(frozen=True)
class DefectFieldSpec:
    key: str                                  # same key as the domain's DEFECT_FIELDS
    label: str                                # already translated
    kind: Literal["number", "bool", "choice"]
    options: tuple[tuple[str, str], ...] = () # choice: (value, translated label)
    placeholder: str = ""
    min_value: float | None = None
```

`choice` is included now (backed by the existing
`PropertiesDialog.add_combo_field`) even though no current defect uses
it, since enum-like fault modes are the next obvious need; it gets its
own unit test.

`DefectDialog` gains:
- `add_defect_field(spec, value)` — dispatches to `add_number_field` /
  `add_bool_field` / `add_combo_field`, stores the widget keyed by
  `spec.key`;
- `defect_widget(key)` — returns that widget;
- `note_field` — the "Note (optional)" line edit, always added last by
  the base builder;
- `defect_values()` — `{key: value}` for every field: number → `float`,
  bool → `bool`, choice → the option's value.

These replace the ad-hoc `dialog._field_k` / `_field_stuck` /
`_field_note` attributes.

### `NodeItem`

- New hook `defect_fields(self) -> list[DefectFieldSpec]`, default `[]`.
- `build_defect_dialog()` becomes generic: `[]` → `None` (no menu entry,
  as today); otherwise builds a `DefectDialog` titled
  "Simulate defect — {name}" (name from `palette_meta().name`, falling
  back to the class name — logic moved up from `DirectionalValveItem`),
  adds one field per spec prefilled from
  `self._domain_node.defect_value(spec.key)` (when there is no domain
  node yet, from `self.properties.get(spec.key)`; `None` leaves the
  field at its kind's empty/False default), then the note field.
- `apply_defect_from_dialog()` becomes generic: Restore →
  `{"action": "clear_defect"}`; Apply →
  `{"action": "set_defect", **dialog.defect_values()}`; `"note"` added
  only when non-empty.
- Both stay overridable for a component that ever needs a custom dialog.

### `DirectionalValveItem`

Its `build_defect_dialog` / `apply_defect_from_dialog` are replaced by:

```python
def defect_fields(self):
    if self.domain != "hydraulic":
        return []
    return [
        DefectFieldSpec("k", <"Conductance k (m³/s/√Pa)">, "number",
                        placeholder="ex: 1.5e-8", min_value=0),
        DefectFieldSpec("stuck", <"Valve stuck (won't switch)">, "bool"),
    ]
```

Field order, labels, placeholder, validation (k required, > 0 per the
existing reject-zero/negative tests) and emitted payloads stay
identical.

### i18n

- The title string moves from context `DirectionalValveItem` to
  `NodeItem`; the note label/placeholder move to `DefectDialog`
  (or `NodeItem`). pt_BR translations are carried over to the new
  contexts, catalogs regenerated (`pylupdate6`, never
  `--no-obsolete`), `.qm` rebuilt.
- Labels are translated inside methods (no module-level `tr()`).
- `tests/test_pt_br_translation_loads.py`'s defect-dialog assertions
  must still pass in both languages.

## Testing

- **Mixin unit tests** (`tests/test_defect_mixin.py`, a minimal fake
  node): set → attribute changed + `defect_active`; clear → restored;
  snapshot captured once across repeated sets; unknown key ignored;
  missing attribute ignored; type coercion (float, bool, str);
  `defect_value`; `defect_note` on set and clear; `_on_defect_changed`
  called on both; non-defect commands reach `super().handle_command`.
- **Dialog unit tests**: `add_defect_field` for each kind,
  `defect_values()` conversion, generic `build_defect_dialog` /
  `apply_defect_from_dialog` on a fake item (prefill from domain node,
  prefill fallback to properties, empty spec list → `None`, note
  omitted when blank, restore payload).
- **Regression**: the existing directional-valve defect suites
  (`test_directional_valve_defect_simulation.py`,
  `test_directional_valve_hydraulic_k_helper.py`,
  `test_valve_3_2_ways_defect_domain.py`,
  `test_directional_valve_4_2_5_2_hydraulic.py`,
  `test_directional_valve_item_defect_dialog_shared.py`,
  `test_valve_3_2_ways_defect_dialog.py`,
  `test_valve_4_2_ways_defect_dialog.py`, `test_frame_recorder.py`,
  `test_node_item_defect_hooks.py`, `test_context_menu_simulate_mode.py`,
  `test_pt_br_translation_loads.py`) keep their assertions on behavior
  and payloads. Only references to removed private names
  (`_stuck_defect`, `_k_default`, `_defect_note`, `dialog._field_*`)
  and fake domain nodes (which now need `defect_value`) are updated.
- Full test suite green before merge.
