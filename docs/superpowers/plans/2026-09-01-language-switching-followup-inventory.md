# Follow-up: per-node-type string migration inventory

Generated 2026-09-01 as a tracked follow-up to
[2026-09-01-language-switching.md](2026-09-01-language-switching.md)
(Task 12) -- not migrated in that plan per the spec's non-goal on 100%
v1 string coverage.

## Pattern

Identical to Tasks 4-9 of the parent plan: wrap each literal in
`self.tr("...")`, rewrite Portuguese source text to English, add the
original Portuguese text as the `pt_BR.ts` translation for that string
(re-run `pylupdate6` per Task 10 Step 3 to pick up the new `tr()` calls,
then fill in `circuiteditor_pt_BR.ts` and recompile via
`scripts/compile_translations.py`).

**Important inheritance pattern:** Many property-dialog field labels and
`palette_meta(name=...)` display names are defined in per-node `build_properties_dialog()`,
`palette_meta()`, or similar methods that may be inherited by subclasses
(e.g., `CylinderItem`'s properties methods inherited by `DoubleActingCylinder`
or `SingleActingCylinder`). When a base class's method containing `self.tr(...)`
is invoked by a subclass via `super()` without being overridden, Qt's runtime
translation context resolves to the subclass's RUNTIME class, but `pylupdate6`'s
static extraction attributes it to the base class — causing silent missing
translations for subclass callers.

**Fix:** Use `QCoreApplication.translate("<ExplicitClassName>", ...)` instead
of `self.tr(...)` whenever the method might be called by an unrelated subclass.
See `node_item.py`'s `extend_context_menu()` and `properties_dialog.py`'s uses
(fixed in Task 11's round) for worked examples.

## Inventory

graphics/items/base/nodes/accumulator.py:32:    def palette_meta(cls):
graphics/items/base/nodes/accumulator.py:102:        dialog._field_v0 = dialog.add_number_field(
graphics/items/base/nodes/accumulator.py:108:        dialog._field_p0 = dialog.add_number_field(
graphics/items/base/nodes/check_valve/check_valve.py:50:    def palette_meta(cls):
graphics/items/base/nodes/check_valve/check_valve.py:141:        dialog._field_piloted = dialog.add_bool_field(
graphics/items/base/nodes/check_valve/check_valve.py:144:        dialog._field_pilot_mirrored = dialog.add_bool_field(
graphics/items/base/nodes/check_valve/throttle_check_valve.py:34:    def palette_meta(cls):
graphics/items/base/nodes/check_valve/throttle_check_valve.py:99:            dialog._field_k = dialog.add_number_field(
graphics/items/base/nodes/check_valve/throttle_check_valve.py:106:            dialog._field_delay = dialog.add_number_field(
graphics/items/base/nodes/coil/coil_item.py:104:        dialog._name_field = dialog.add_text_field(
graphics/items/base/nodes/coil/relay_coil.py:15:    def palette_meta(cls):
graphics/items/base/nodes/coil/solenoid_coil.py:15:    def palette_meta(cls):
graphics/items/base/nodes/cylinder/cylinder_item.py:463:            combo = dialog.add_combo_field(f"Sensor {pos}", sensor_options, current=current_label)
graphics/items/base/nodes/cylinder/cylinder_item.py:464:            name_field = dialog.add_text_field("  Nome", placeholder="ex: A1", value=current_name)
graphics/items/base/nodes/cylinder/cylinder_item.py:488:        dialog._combo_default_state = dialog.add_combo_field(
graphics/items/base/nodes/cylinder/double_acting_cylinder.py:37:    def palette_meta(cls):
graphics/items/base/nodes/cylinder/double_acting_cylinder.py:97:            dialog._field_bore      = dialog.add_number_field(
graphics/items/base/nodes/cylinder/double_acting_cylinder.py:100:            dialog._field_rod       = dialog.add_number_field(
graphics/items/base/nodes/cylinder/double_acting_cylinder.py:103:            dialog._field_stroke    = dialog.add_number_field(
graphics/items/base/nodes/cylinder/double_acting_cylinder.py:106:            dialog._field_ext_force = dialog.add_number_field(
graphics/items/base/nodes/cylinder/single_acting_cylinder.py:43:    def palette_meta(cls):
graphics/items/base/nodes/cylinder/single_acting_cylinder.py:112:            dialog._field_bore      = dialog.add_number_field(
graphics/items/base/nodes/cylinder/single_acting_cylinder.py:115:            dialog._field_stroke    = dialog.add_number_field(
graphics/items/base/nodes/cylinder/single_acting_cylinder.py:118:            dialog._field_spring_k  = dialog.add_number_field(
graphics/items/base/nodes/cylinder/single_acting_cylinder.py:121:            dialog._field_ext_force = dialog.add_number_field(
graphics/items/base/nodes/directional_valve/directional_valve_item.py:743:            dialog._field_k = dialog.add_number_field(
graphics/items/base/nodes/directional_valve/directional_valve_item.py:795:        dialog._combo_left = dialog.add_combo_field("Atuador esquerdo", options, current=current_label("left"))
graphics/items/base/nodes/directional_valve/directional_valve_item.py:796:        dialog._field_timer_left = dialog.add_number_field(
graphics/items/base/nodes/directional_valve/directional_valve_item.py:800:        dialog._field_latch_left = dialog.add_bool_field(
graphics/items/base/nodes/directional_valve/directional_valve_item.py:804:        dialog._combo_right = dialog.add_combo_field("Atuador direito", options, current=current_label("right"))
graphics/items/base/nodes/directional_valve/directional_valve_item.py:805:        dialog._field_timer_right = dialog.add_number_field(
graphics/items/base/nodes/directional_valve/directional_valve_item.py:809:        dialog._field_latch_right = dialog.add_bool_field(
graphics/items/base/nodes/directional_valve/directional_valve_item.py:819:        dialog._combo_default_side = dialog.add_combo_field(
graphics/items/base/nodes/directional_valve/directional_valve_item.py:894:    # palette_meta(), reused here as the title.
graphics/items/base/nodes/directional_valve/directional_valve_item.py:904:        meta = type(self).palette_meta()
graphics/items/base/nodes/directional_valve/directional_valve_item.py:905:        # meta can be None (NodeItem.palette_meta()'s default for
graphics/items/base/nodes/directional_valve/directional_valve_item.py:912:        dialog._field_k = dialog.add_number_field(
graphics/items/base/nodes/directional_valve/directional_valve_item.py:916:        dialog._field_stuck = dialog.add_bool_field(
graphics/items/base/nodes/directional_valve/valve_2_2_ways.py:26:    def palette_meta(cls):
graphics/items/base/nodes/directional_valve/valve_3_2_ways.py:26:    def palette_meta(cls):
graphics/items/base/nodes/directional_valve/valve_4_2_ways.py:26:    def palette_meta(cls):
graphics/items/base/nodes/directional_valve/valve_4_3_ways.py:35:    def palette_meta(cls):
graphics/items/base/nodes/directional_valve/valve_5_2_ways.py:26:    def palette_meta(cls):
graphics/items/base/nodes/exhaust.py:17:    def palette_meta(cls):
graphics/items/base/nodes/expandable/ground.py:20:    def palette_meta(cls):
graphics/items/base/nodes/expandable/pressure_line.py:47:    def palette_meta(cls):
graphics/items/base/nodes/expandable/voltage_source.py:20:    def palette_meta(cls):
graphics/items/base/nodes/fixed_displacement_motor.py:20:    def palette_meta(cls):
graphics/items/base/nodes/fixed_displacement_motor.py:120:        dialog._field_d = dialog.add_number_field(
graphics/items/base/nodes/fixed_displacement_motor.py:125:        dialog._combo_mode = dialog.add_combo_field(
graphics/items/base/nodes/fixed_displacement_motor.py:136:        dialog._field_t = dialog.add_number_field(
graphics/items/base/nodes/fixed_displacement_motor.py:141:        dialog._field_omega = dialog.add_number_field(
graphics/items/base/nodes/fixed_displacement_motor.py:151:        dialog._field_p_max = dialog.add_number_field(
graphics/items/base/nodes/fixed_displacement_motor.py:156:        dialog._field_n_max = dialog.add_number_field(
graphics/items/base/nodes/logic_valve/and_valve.py:17:    def palette_meta(cls):
graphics/items/base/nodes/logic_valve/or_valve.py:17:    def palette_meta(cls):
graphics/items/base/nodes/node_descriptor.py:25:    Returned by each concrete NodeItem's ``palette_meta()`` classmethod.
graphics/items/base/nodes/node_item.py:94:    def palette_meta(cls) -> "PaletteMeta | None":
graphics/items/base/nodes/node_item.py:105:            def palette_meta(cls):
graphics/items/base/nodes/pressure_source.py:17:    def palette_meta(cls):
graphics/items/base/nodes/pumps/centrifugal_pump.py:18:    def palette_meta(cls):
graphics/items/base/nodes/pumps/centrifugal_pump.py:37:            dialog._field_h = dialog.add_number_field(
graphics/items/base/nodes/pumps/centrifugal_pump.py:42:            dialog._field_qmax = dialog.add_number_field(
graphics/items/base/nodes/pumps/fixed_displacement_pump.py:18:    def palette_meta(cls):
graphics/items/base/nodes/pumps/fixed_displacement_pump.py:36:            dialog._field_Q = dialog.add_number_field(
graphics/items/base/nodes/relief_valve.py:41:    def palette_meta(cls):
graphics/items/base/nodes/relief_valve.py:90:            dialog._field_p_set = dialog.add_number_field(
graphics/items/base/nodes/relief_valve.py:95:            dialog._field_piloted = dialog.add_bool_field(
graphics/items/base/nodes/reservoir.py:17:    def palette_meta(cls):
graphics/items/base/nodes/switch/contact.py:84:    def palette_meta(cls):
graphics/items/base/nodes/switch/contact.py:297:        dialog._combo_contact = dialog.add_combo_field(
graphics/items/base/nodes/switch/contact.py:311:        dialog._combo_relay = dialog.add_combo_field(
graphics/items/base/nodes/switch/contact.py:316:        dialog._field_latch = dialog.add_bool_field(

## Suggested batching

Group by node file (each file's fields/labels form one self-contained
task, same shape as Task 9's per-file steps) rather than by string type
-- a reviewer can approve/reject one node type's migration independently
of another's.
