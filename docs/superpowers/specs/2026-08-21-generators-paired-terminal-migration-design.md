# Migrating the 4 topology generators to paired-terminal buses — design

Date: 2026-08-21
Status: approved for implementation plan

## Context and problem

`2026-08-21-expandable-items-junction-redesign-design.md` replaced the old
`ExpandableItem` N-anchor bus (`Ground`/`VoltageSource`/`PressureLine` holding
`properties["anchors"] = ["X1", "X2", ...]` on one node) with two ordinary
single-anchor `NodeItem`s (`node_a`, `node_b`) joined by an ordinary
`ConnectionItem`, with extra taps modeled as `JunctionNodeItem`s spliced into
that connection. That spec explicitly scoped out the four topology generators
(`circuit_generator/cascade_layout.py`, `layout_engine.py`,
`step_by_step_layout.py`, `step_by_step_electric_layout.py`), which still
write the old format and now error against the new node classes.

This spec covers migrating those four generators to emit the new format.

All four still write `properties["anchors"]` for PressureLine buses
(pneumatic: `cascade_layout.py`, `layout_engine.py`, `step_by_step_layout.py`)
and Ground/VoltageSource buses (electric:
`step_by_step_electric_layout.py`). Each one also implements — nearly
verbatim, copy-pasted across files ("Ported from step_by_step_layout.py,
same names and body") — a same-bus column-collision resolver
(`_resolve_conflict`/`_pl_anchor_x`/`_nearest_pl_anchor`,
`pl_anchor_used`/`_mem_pl_used_x`) that keeps two different taps on the same
bus from landing on the same X column (which would draw their vertical drops
on top of each other). This scoped rule is unrelated to the separate
`avoid_global_x`/`or_source_x_used` mechanism in `cascade_layout.py`, which
avoids X-collisions between unrelated connections converging on an `OrValve`
input — that mechanism is untouched by this spec.

## Decision

Extract the same-bus collision resolver into one shared module,
`circuit_generator/rail.py`, used by all four generators. Keep the
topology/layout split exactly as it is today: topology
(`methods/cascade.py`, `methods/step_by_step_pneumatic.py`,
`methods/step_by_step_electric.py`) is **unchanged** — it keeps emitting one
placeholder node per bus with `properties["anchors"]` and connections
addressed as `{"node": bus_id, "anchor": "X{i}"}`, exactly as today. Only the
layout files change: where each one currently prunes the anchor list down to
the actually-used range and writes it back to `properties["anchors"]`, it
instead calls `rail.py` to materialize the real paired-terminal structure and
rewrites the connections that referenced the bus.

## `circuit_generator/rail.py`

### Inputs

- The bus's placeholder node id (`bus_id`) and its `node_type`
  (`"pressure_line"`, `"ground"`, or `"voltage_source"` — determines
  `node_b`'s type, see below).
- The list of symbolic tap names actually in use (`["X1", "X3", "X7", ...]`,
  already pruned by the caller the same way as today — `rail.py` doesn't
  decide *which* anchors survived pruning, only what to do with the survivors).
- Per tap: its owning connection dict (so `rail.py` can rewrite it in place),
  the owner's y-position (needed by the collision heuristic, same signature
  as today's `_resolve_conflict`), a desired x, and which side of the bus it
  approaches from (mirrors today's `side`/`push_dir` params).
- The bus's fixed y and the x-range it must reach (already computed by each
  generator's own reach/sizing logic — `rail.py` does not decide how far the
  bus extends, only where taps land inside the range it's given).

### Behavior

1. **Resolve final x per tap**, reusing `_resolve_conflict`'s shape (push to
   the nearest free slot in the direction implied by whether the two taps'
   owners are on the same or opposite sides of the bus) but in continuous x
   instead of discrete `X{i}` grid indices. Minimum spacing between adjacent
   taps stays `_M.pl_spacing` (same constant, same value, just no longer a
   hard grid — a tap can land anywhere as long as it clears its neighbors by
   at least this much).
2. **Extremes reuse `node_a`/`node_b` directly.** A tap resolved to the
   leftmost or rightmost x of the bus's final range attaches to `node_a`'s or
   `node_b`'s own anchor — no `JunctionNodeItem` is created for it. Only taps
   strictly between the two ends spawn a real `JunctionNodeItem`.
3. **Materialize the nodes.** `node_a` **keeps the placeholder's id and
   `node_type`** — every generator's existing bookkeeping keyed by `bus_id`
   (`node_pos[pl_id]`, `pl_node_map`, etc.) keeps working unmodified. Its
   `properties["anchors"]` key is dropped. `node_b` gets a fresh id and
   `node_type` `"pressure_line_terminal"` (PressureLine bus) or `"junction"`
   (Ground/VoltageSource bus). Each interior tap gets a fresh
   `"junction"`-typed node.
4. **Materialize the rail connections.** Sorts `node_a` + interior junctions
   + `node_b` by resolved x and adds the chain of `ConnectionItem` dicts
   between consecutive points to `data["connections"]`.
5. **Return the rewrite map**: `{"X{i}": (real_node_id, real_anchor_name)}`
   — `"X1"` for `node_a`/`node_b`-anchored taps (matches the anchor name
   both `PressureLine`/`Ground`/`VoltageSource`'s `node_a` and
   `PressureLineTerminal`'s `node_b` already use), `"J"` for junction-typed
   endpoints (interior taps, and `node_b` when it's Ground/VoltageSource's
   bare `JunctionNodeItem`).

### Caller responsibility (unchanged per generator)

Each of the four layout files keeps its own reach/sizing calculation (how far
left/right the bus must extend) and its own decision of which symbolic
anchors survive pruning — that logic differs enough between cascade,
step-by-step pneumatic, and step-by-step electric that it isn't worth
unifying. Only the collision-resolution-and-materialization step, which was
identical dead-weight duplication, moves into `rail.py`. After calling it,
each caller walks the connections it owns and applies the returned rewrite
map to their `source`/`target` node/anchor fields.

## Dead code removed by this change

- `_resolve_conflict`, `_pl_anchor_x`, `_nearest_pl_anchor`,
  `pl_anchor_used`, `_mem_pl_used_x`'s discrete-grid bodies in
  `cascade_layout.py`, `layout_engine.py`, `step_by_step_layout.py`,
  `step_by_step_electric_layout.py` — replaced by calls into `rail.py`.
- Any remaining reference to `properties["anchors"]` in the four layout
  files' output.

## Out of scope

- `avoid_global_x`/`or_source_x_used` (OrValve input collision-avoidance) —
  unrelated mechanism, untouched.
- Topology files (`methods/cascade.py`, `methods/step_by_step_pneumatic.py`,
  `methods/step_by_step_electric.py`) — unchanged.
- Any change to the interactive editor path — already covered by
  `2026-08-21-expandable-items-junction-redesign-design.md`.

## Testing

- `rail.py` unit tests: column-collision resolution across several
  owner-y/side combinations (mirrors today's `_resolve_conflict` test
  coverage), extremes reusing `node_a`/`node_b` instead of spawning a
  junction, minimum-spacing enforcement between adjacent interior taps.
- One round-trip test per generator: run the generator, load the resulting
  JSON through the real node classes, assert no `properties["anchors"]`
  remains and no two taps on the same bus share an x column.
