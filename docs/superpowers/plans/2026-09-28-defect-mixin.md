# DefectMixin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the directional-valve-only defect plumbing with a generic, declarative mechanism (domain `DefectMixin` + UI `DefectFieldSpec`), with no behavior change.

**Architecture:** Domain nodes declare `DEFECT_FIELDS = {command_key: attribute}`; `DefectMixin` snapshots/restores those attributes and derives `defect_active`. Items declare `defect_fields() -> list[DefectFieldSpec]`; `NodeItem` builds the dialog and emits the command generically.

**Tech Stack:** Python 3.14, PyQt6, pytest (`QT_QPA_PLATFORM=offscreen python -m pytest tests -q`).

**Spec:** `docs/superpowers/specs/2026-09-28-defect-mixin-design.md`

## Global Constraints

- Command format unchanged: `{"action": "set_defect", "k": float, "stuck": bool, "note"?: str}`, `{"action": "clear_defect", "note"?: str}`; `"note"` omitted when blank.
- Pneumatic directional valves keep no defect dialog.
- English, terse code comments (repo convention).
- i18n: `QCoreApplication.translate("<ExplicitClass>", ...)` in base-class methods; never `pylupdate6 --no-obsolete`.

## Spec deviation (found while planning)

`DirectionalValve` (and `Contact`) override `handle_command`, so they run *before* the mixin in the MRO — the mixin cannot intercept first on its own. Resolution: the mixin exposes `handle_defect_command(cmd) -> bool` (True if consumed). Its own `handle_command` uses it for subclasses that don't override; subclasses that override start with `if self.handle_defect_command(command): return`.

## Review Focus

1. `set_defect` with only some keys (e.g. just `stuck`) must keep other fields' current values — tested in Task 1.
2. Repeated `set_defect` must not overwrite the snapshot with a defective value (restore must reach the *healthy* value) — tested in Task 1.
3. Dialog opened before the first sim step (no domain node yet) must prefill `k` from properties — existing tests cover it, kept in Task 4.
4. `k` field still rejects 0/negative (OK button disabled) — existing tests kept in Task 4.
5. pt_BR title/labels still translate after context moves — Task 5.

---

### Task 1: `DefectMixin`

**Files:** Create `simulation/nodes/defect.py`, `tests/test_defect_mixin.py`.

**Produces:** `DefectMixin` with `DEFECT_FIELDS`, `handle_defect_command(cmd) -> bool`, `handle_command`, `defect_active`, `defect_value(key)`, `defect_note`, `_on_defect_changed()`.

- [ ] Write tests (fake `_FakeNode(DefectMixin, Node)` with `DEFECT_FIELDS = {"k": "k", "stuck": "stuck_defect", "mode": "mode", "n": "n", "ghost": "ghost_attr"}`, attrs `k=1.0, stuck_defect=False, mode="none", n=3`, no `ghost_attr`): fresh inactive; set changes attrs + active; partial set keeps others; repeated set keeps first snapshot so clear restores healthy; unknown key ignored; missing attribute ignored; coercion float/bool/str/int; setting value back to original reads inactive; `defect_value` mapped/unmapped/missing; note on set/clear/default; `_on_defect_changed` called on set and clear; non-defect command reaches `super().handle_command`; `handle_defect_command` returns True/False.
- [ ] Run → fail (module missing).
- [ ] Implement `simulation/nodes/defect.py` (see code in repo).
- [ ] Run → pass. Commit `feat: add generic DefectMixin for simulation nodes`.

### Task 2: Migrate `DirectionalValve` domain

**Files:** Modify `simulation/nodes/directional_valve/directional_valve.py`, `simulation/report/frame_recorder.py:163,168`; tests `test_directional_valve_defect_simulation.py`, `test_directional_valve_hydraulic_k_helper.py`, `test_valve_3_2_ways_defect_domain.py`.

- [ ] Update tests: `_stuck_defect` → `stuck_defect`, `_defect_note` → `defect_note`; k-helper tests assert `defect_active`/restore behavior instead of `_k_default` (the "no k on pneumatic" test asserts `not hasattr(valve, "k")`).
- [ ] Run → fail on renamed attrs.
- [ ] `class DirectionalValve(DefectMixin, Node)` with `DEFECT_FIELDS = {"k": "k", "stuck": "stuck_defect"}`; `self.stuck_defect = False`; `handle_command` starts with `if self.handle_defect_command(command): return`; delete `_apply_defect_command`, `_clear_defect`, `defect_active`, `_defect_note`, `_k_default`; `_init_hydraulic_k` = validate + `self.k = float(k)`; `_compute_body_state` reads `self.stuck_defect`. FrameRecorder reads `defect_note`.
- [ ] Run defect/valve/frame_recorder tests → pass. Commit `refactor: directional valves use DefectMixin`.

### Task 3: `DefectFieldSpec` + `DefectDialog` helpers

**Files:** Modify `graphics/utils/defect_dialog.py`; create `tests/test_defect_dialog_fields.py`.

**Produces:** `DefectFieldSpec(key, label, kind, options=(), placeholder="", min_value=None)`; `DefectDialog.add_defect_field(spec, value)`, `defect_widget(key)`, `add_note_field()`, `note_field`, `note_text() -> str`, `defect_values() -> dict`.

- [ ] Tests: number field prefilled + `defect_values` float; number `None` value leaves empty; bool; choice prefill + value; `min_value` rejects 0 (OK disabled); note field text stripped; `defect_widget` returns widget.
- [ ] Run → fail. Implement. Number fields are `required=True`. Choice uses `add_combo_field(label, list(options), current=value)`, value read via `currentData()`.
- [ ] Run → pass. Commit `feat: declarative DefectFieldSpec for defect dialogs`.

### Task 4: Generic `NodeItem` build/apply + `DirectionalValveItem.defect_fields`

**Files:** Modify `graphics/items/base/nodes/node_item.py` (build/apply defaults + `defect_fields`), `graphics/items/base/nodes/directional_valve/directional_valve_item.py` (replace ~60 lines with `defect_fields`); tests `test_directional_valve_item_defect_dialog_shared.py`, `test_valve_3_2_ways_defect_dialog.py`, `test_valve_4_2_ways_defect_dialog.py`, new `tests/test_node_item_generic_defect_dialog.py`.

- [ ] Update existing tests: `dialog._field_k` → `dialog.defect_widget("k")`, `_field_stuck` → `defect_widget("stuck")`, `_field_note` → `dialog.note_field`; fake domain nodes gain `defect_value(key)` returning `{"k": self.k, "stuck": self.stuck}`.
- [ ] New generic tests on a fake item with `defect_fields()` returning number+bool+choice: `[]` → `None`; title uses palette name fallback to class name; prefill from domain node `defect_value`; prefill fallback to `properties` without domain node; apply emits `set_defect` with all keys typed; note omitted when blank; restore emits `clear_defect` (+note).
- [ ] Run → fail. Implement:
  - `NodeItem.defect_fields()` → `[]`.
  - `NodeItem.build_defect_dialog()`: specs empty → `None`; title `QCoreApplication.translate("NodeItem", "Simulate defect — {0}").format(label)`; value per spec: `domain_node.defect_value(key)` if domain node has `defect_value`, else `self.properties.get(key)`; then `dialog.add_note_field()`.
  - `NodeItem.apply_defect_from_dialog()`: generic payloads.
  - `DirectionalValveItem.defect_fields()`: hydraulic only, labels via `QCoreApplication.translate("DirectionalValveItem", ...)` (same context/strings as today).
- [ ] Run item/menu/pt_BR tests. Commit `refactor: generic defect dialog on NodeItem`.

### Task 5: i18n catalogs + full suite

**Files:** `resources/i18n/circuiteditor_{en,pt_BR}.ts` (+ `.qm`).

- [ ] Add pt_BR entries by hand: context `NodeItem`: "Simulate defect — {0}" → "Simular defeito — {0}"; context `DefectDialog`: "Note (optional)" → "Nota (opcional)", "e.g. debris in the orifice" → "ex.: sujeira no orifício". Mirror source-only entries in en.ts.
- [ ] Compile with `scripts/compile_translations.py` (PATH includes venv Scripts).
- [ ] Extend `test_directional_valve_item_defect_dialog_translates` with the note label in both languages.
- [ ] Full suite green. Commit `i18n: translations for generic defect dialog`.
