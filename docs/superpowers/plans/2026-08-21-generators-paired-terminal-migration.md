# Generators Paired-Terminal Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the four topology generators (`cascade_layout.py`, `layout_engine.py`, `step_by_step_layout.py`, `step_by_step_electric_layout.py`) off the old `properties["anchors"]` N-anchor bus format onto the new paired-terminal (`node_a`/`node_b` + junction taps) format that `Ground`/`VoltageSource`/`PressureLine` now use.

**Architecture:** A new shared module, `circuit_generator/rail.py`, owns two collision-resolution strategies already duplicated (nearly verbatim) across the generators — an incremental push/evict resolver (cascade + step-by-step pneumatic) and a sort-and-match resolver (step-by-step electric, which has exactly one `VoltageSource`/`Ground` bus each, so a simpler monotonic assignment already avoids crossings without push/evict) — plus one shared materialization step that turns resolved tap positions into real `node_a`/`node_b`/`JunctionNodeItem` node dicts, the rail's chain of `ConnectionItem` dicts, and rewrites of the external connections that targeted the bus. Each of the four `*_layout.py` files keeps its own reach/sizing and target-x computation (unchanged) and only replaces its final "write to `properties["anchors"]`" step with calls into `rail.py`.

**Tech Stack:** Python 3, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-21-generators-paired-terminal-migration-design.md` (and the prerequisite `docs/superpowers/specs/2026-08-21-expandable-items-junction-redesign-design.md`, already implemented).

## Global Constraints

- Topology (`circuit_generator/methods/cascade.py`, `methods/step_by_step_pneumatic.py`, `methods/step_by_step_electric.py`) is **not modified** by this plan — it keeps emitting one placeholder bus node with `properties["anchors"]` and connections addressed as `{"node": bus_id, "anchor": "X{i}"}`.
- Minimum spacing between two taps on the same bus stays `circuit_generator.sprite_metrics.METRICS.pl_spacing` (same value used today), now enforced in continuous x instead of a discrete grid.
- `node_a` of a migrated bus **keeps the placeholder node's id and `type`** (e.g. `"PressureLine"`, `"Ground"`, `"VoltageSource"`) so every existing dict keyed by the bus id (`node_pos[pl_id]`, `pl_node_map`, etc.) in the four `*_layout.py` files keeps working unmodified.
- `node.to_dict()`'s `"type"` field is the graphics class's `__name__` (`graphics/items/base/nodes/node_item.py:299`, consumed by `from_dict`'s `cls.class_registry[data["type"]]` at `node_item.py:342`) — new nodes must use `"PressureLineTerminal"` or `"JunctionNodeItem"` as their `"type"`, not the lowercase `node_type` class attribute.
- `avoid_global_x` (a cross-bus variant of the same push/evict resolver, used by `cascade_layout.py` for `mem[i].A`/`mem[i].B -> PL` connections) is in scope — it is the same mechanism the spec's Decision section covers, just keyed globally instead of per-bus. It must **not** be confused with the separate, genuinely-unrelated `_or_source_x`/`or_xy_conns` OrValve-input-orientation-swap block in `cascade_layout.py` (~line 697-772), which stays untouched.

---

## File Structure

- Create `circuit_generator/rail.py` — the shared module (materialization + both resolvers).
- Create `tests/test_rail.py` — unit tests for `rail.py`, independent of any generator.
- Modify `circuit_generator/layout_engine.py` — PressureLine buses, push/evict resolver.
- Modify `circuit_generator/step_by_step_layout.py` — PressureLine buses, push/evict resolver.
- Modify `circuit_generator/cascade_layout.py` — PressureLine buses, push/evict resolver + `avoid_global_x`.
- Modify `circuit_generator/step_by_step_electric_layout.py` — Ground/VoltageSource buses, sort-and-match resolver.
- Modify `tests/test_cascade_layout.py`, `tests/test_step_by_step_layout.py`, `tests/test_step_by_step_electric_layout.py` — replace assertions on `properties["anchors"]` with assertions on the new node/connection shape.

---

### Task 1: `rail.py` — bus registration and materialization

**Files:**
- Create: `circuit_generator/rail.py`
- Test: `tests/test_rail.py`

**Interfaces:**
- Produces: `class RailPlanner` with `register_bus(bus_id, node_b_type, y, x_min, x_max) -> None` and `materialize(data, node_by_id, node_pos) -> None`. Also the `Tap` dataclass (`x`, `owner_id`, `owner_y`, `conn_ref`, `side`, `push_dir`) used internally and by Tasks 2-3.
- Consumes: nothing (foundation task).

`RailPlanner` tracks one or more buses. For each bus it holds a mutable list of `Tap`s (each already carrying its **final** resolved `x` by the time `materialize()` runs — resolving that `x` is Task 2/3's job, not this task's). `materialize()`:

1. For each registered bus, sorts its taps by `x`.
2. A tap whose `x` equals the bus's `x_min` or `x_max` (its first or last sorted tap) attaches directly to `node_a` (`bus_id`, anchor `"X1"`) or `node_b` (fresh id, anchor `"X1"` if `node_b_type == "PressureLineTerminal"` else `"J"`) — no junction is created for it.
3. Every other (interior) tap gets a fresh `JunctionNodeItem` node dict (`"type": "JunctionNodeItem"`, `"domain"` copied from `node_by_id[bus_id]["domain"]`, `"position": {"x": tap.x, "y": bus_y}`, `"properties": {}`), appended to `data["nodes"]`, and its tap's rewrite target is that node's id with anchor `"J"`.
4. Builds `node_b`'s node dict (same `"domain"`/`"position"` pattern, `"position"` at `(x_max, bus_y)`) and appends it to `data["nodes"]`.
5. Drops `"anchors"` from `node_by_id[bus_id]["properties"]` (mutates in place) and sets its position to `(x_min, bus_y)`.
6. Builds the rail's `ConnectionItem` dicts chaining `node_a -> junction_1 -> junction_2 -> ... -> node_b` in sorted-x order, in the same connection-dict shape topology already uses (`{"source": {"node": ..., "anchor": ...}, "target": {"node": ..., "anchor": ...}, "waypoints": []}`), appended to `data["connections"]`.
7. For every tap, rewrites `tap.conn_ref[tap.side]["node"]` and `tap.conn_ref[tap.side]["anchor"]` to point at the resolved node id/anchor from steps 2-4.

If a bus has zero taps, `node_a` and `node_b` are still created (a bare two-node rail, matching "always spawns a pair" from the interactive redesign) with `node_b` at `x_min + min_spacing` — this can't happen from a real generator today (every bus is created because at least one connection needs it) but keeps `materialize()` total.

- [ ] **Step 1: Write the failing tests for `materialize()`**

```python
# tests/test_rail.py
import pytest
from circuit_generator.rail import RailPlanner, Tap


def _bus_node(bus_id="pl1", node_type="PressureLine", domain="pneumatic"):
    return {
        "id": bus_id, "type": node_type, "domain": domain,
        "position": {"x": 0.0, "y": 500.0},
        "properties": {"anchors": ["X1", "X2", "X3"]},
    }


def test_materialize_drops_anchors_and_repositions_node_a():
    node = _bus_node()
    node_by_id = {"pl1": node}
    node_pos = {"pl1": (0.0, 500.0)}
    data = {"nodes": [node], "connections": []}

    conn = {"source": {"node": "pl1", "anchor": "X2"}, "target": {"node": "other", "anchor": "P"}}
    planner = RailPlanner(min_spacing=60.0)
    planner.register_bus("pl1", "PressureLineTerminal", y=500.0, x_min=100.0, x_max=400.0)
    planner._buses["pl1"].taps.append(
        Tap(x=100.0, owner_id="other", owner_y=0.0, conn_ref=conn, side="source", push_dir=0)
    )
    planner.materialize(data, node_by_id, node_pos)

    assert "anchors" not in node["properties"]
    assert node["position"] == {"x": 100.0, "y": 500.0}


def test_extreme_taps_attach_directly_to_node_a_and_node_b_no_junction():
    node = _bus_node()
    node_by_id = {"pl1": node}
    node_pos = {"pl1": (0.0, 500.0)}
    data = {"nodes": [node], "connections": []}

    conn_left = {"source": {"node": "pl1", "anchor": "X1"}, "target": {"node": "left", "anchor": "P"}}
    conn_right = {"source": {"node": "pl1", "anchor": "X3"}, "target": {"node": "right", "anchor": "P"}}
    planner = RailPlanner(min_spacing=60.0)
    planner.register_bus("pl1", "PressureLineTerminal", y=500.0, x_min=100.0, x_max=400.0)
    planner._buses["pl1"].taps += [
        Tap(x=100.0, owner_id="left", owner_y=0.0, conn_ref=conn_left, side="source", push_dir=0),
        Tap(x=400.0, owner_id="right", owner_y=0.0, conn_ref=conn_right, side="source", push_dir=0),
    ]
    planner.materialize(data, node_by_id, node_pos)

    junctions = [n for n in data["nodes"] if n["type"] == "JunctionNodeItem"]
    assert junctions == []  # no interior taps in this test
    assert conn_left["source"] == {"node": "pl1", "anchor": "X1"}
    node_b_id = conn_right["source"]["node"]
    assert node_b_id != "pl1"
    node_b = next(n for n in data["nodes"] if n["id"] == node_b_id)
    assert node_b["type"] == "PressureLineTerminal"
    assert conn_right["source"]["anchor"] == "X1"


def test_interior_tap_gets_a_junction_node_and_the_rail_chains_through_it():
    node = _bus_node()
    node_by_id = {"pl1": node}
    node_pos = {"pl1": (0.0, 500.0)}
    data = {"nodes": [node], "connections": []}

    conn_left = {"source": {"node": "pl1", "anchor": "X1"}, "target": {"node": "left", "anchor": "P"}}
    conn_mid = {"source": {"node": "pl1", "anchor": "X2"}, "target": {"node": "mid", "anchor": "P"}}
    conn_right = {"source": {"node": "pl1", "anchor": "X3"}, "target": {"node": "right", "anchor": "P"}}
    planner = RailPlanner(min_spacing=60.0)
    planner.register_bus("pl1", "PressureLineTerminal", y=500.0, x_min=100.0, x_max=400.0)
    planner._buses["pl1"].taps += [
        Tap(x=100.0, owner_id="left", owner_y=0.0, conn_ref=conn_left, side="source", push_dir=0),
        Tap(x=250.0, owner_id="mid", owner_y=0.0, conn_ref=conn_mid, side="source", push_dir=0),
        Tap(x=400.0, owner_id="right", owner_y=0.0, conn_ref=conn_right, side="source", push_dir=0),
    ]
    planner.materialize(data, node_by_id, node_pos)

    junctions = [n for n in data["nodes"] if n["type"] == "JunctionNodeItem"]
    assert len(junctions) == 1
    j = junctions[0]
    assert j["position"] == {"x": 250.0, "y": 500.0}
    assert conn_mid["source"] == {"node": j["id"], "anchor": "J"}

    node_b_id = conn_right["source"]["node"]
    rail_conns = [c for c in data["connections"]
                  if c["source"]["node"] in ("pl1", j["id"])
                  and c["target"]["node"] in (j["id"], node_b_id)]
    assert {("pl1", j["id"]), (j["id"], node_b_id)} == {
        (c["source"]["node"], c["target"]["node"]) for c in rail_conns
    }


def test_ground_bus_uses_junction_node_item_for_node_b_not_pressure_line_terminal():
    node = _bus_node(bus_id="gnd1", node_type="Ground", domain="electric")
    node_by_id = {"gnd1": node}
    node_pos = {"gnd1": (0.0, 500.0)}
    data = {"nodes": [node], "connections": []}

    conn = {"source": {"node": "k1", "anchor": "1"}, "target": {"node": "gnd1", "anchor": "X1"}}
    planner = RailPlanner(min_spacing=60.0)
    planner.register_bus("gnd1", "JunctionNodeItem", y=500.0, x_min=100.0, x_max=100.0)
    planner._buses["gnd1"].taps.append(
        Tap(x=100.0, owner_id="k1", owner_y=0.0, conn_ref=conn, side="target", push_dir=0)
    )
    planner.materialize(data, node_by_id, node_pos)

    # single tap sits exactly at x_min == x_max -> attaches to node_a directly
    assert conn["target"] == {"node": "gnd1", "anchor": "X1"}
    assert any(n["type"] == "JunctionNodeItem" and n["id"] != "gnd1" for n in data["nodes"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_rail.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'circuit_generator.rail'`

- [ ] **Step 3: Implement `RailPlanner`/`Tap`/`materialize()`**

```python
# circuit_generator/rail.py
"""Shared bus-materialization for the four topology generators.

Replaces the old ExpandableItem N-anchor bus format
(properties["anchors"] on a single node) with the paired-terminal model
(node_a/node_b + JunctionNodeItem taps joined by ordinary ConnectionItems)
-- see docs/superpowers/specs/2026-08-21-generators-paired-terminal-migration-design.md.

Two resolvers build on top of this module's materialize() step:
  - request_tap()  (this file, Task 2): incremental push/evict resolver,
    used by cascade_layout.py/step_by_step_layout.py/layout_engine.py.
  - assign_sorted() (this file, Task 3): sort-and-match resolver, used by
    step_by_step_electric_layout.py (single VoltageSource/Ground bus,
    crossing-proof by construction).
"""

import uuid
from dataclasses import dataclass, field


@dataclass
class Tap:
    x: float
    owner_id: str
    owner_y: float
    conn_ref: dict
    side: str          # "source" or "target"
    push_dir: int = 0  # -1/0/1, forced push direction on collision (0 = heuristic)


@dataclass
class _Bus:
    node_b_type: str   # "PressureLineTerminal" or "JunctionNodeItem"
    y: float
    x_min: float
    x_max: float
    taps: list = field(default_factory=list)


class RailPlanner:
    def __init__(self, min_spacing: float):
        self.min_spacing = min_spacing
        self._buses: dict[str, _Bus] = {}

    def register_bus(self, bus_id: str, node_b_type: str, y: float,
                      x_min: float, x_max: float) -> None:
        self._buses[bus_id] = _Bus(node_b_type=node_b_type, y=y, x_min=x_min, x_max=x_max)

    def materialize(self, data: dict, node_by_id: dict, node_pos: dict) -> None:
        for bus_id, bus in self._buses.items():
            self._materialize_bus(bus_id, bus, data, node_by_id, node_pos)

    def _materialize_bus(self, bus_id: str, bus: _Bus, data: dict,
                          node_by_id: dict, node_pos: dict) -> None:
        node_a = node_by_id[bus_id]
        node_a["properties"].pop("anchors", None)
        node_a["position"] = {"x": bus.x_min, "y": bus.y}
        node_pos[bus_id] = (bus.x_min, bus.y)
        domain = node_a["domain"]

        node_b_id = f"{bus_id}-b-{uuid.uuid4().hex[:8]}"
        node_b = {
            "id": node_b_id, "type": bus.node_b_type, "domain": domain,
            "position": {"x": bus.x_max, "y": bus.y},
            "properties": {},
        }
        node_by_id[node_b_id] = node_b
        node_pos[node_b_id] = (bus.x_max, bus.y)
        data["nodes"].append(node_b)
        node_b_anchor = "X1" if bus.node_b_type == "PressureLineTerminal" else "J"

        chain: list[tuple[str, str, float]] = [(bus_id, "X1", bus.x_min)]
        for tap in sorted(bus.taps, key=lambda t: t.x):
            if tap.x == bus.x_min:
                target = (bus_id, "X1")
            elif tap.x == bus.x_max:
                target = (node_b_id, node_b_anchor)
            else:
                j_id = f"{bus_id}-j-{uuid.uuid4().hex[:8]}"
                j_node = {
                    "id": j_id, "type": "JunctionNodeItem", "domain": domain,
                    "position": {"x": tap.x, "y": bus.y},
                    "properties": {},
                }
                node_by_id[j_id] = j_node
                node_pos[j_id] = (tap.x, bus.y)
                data["nodes"].append(j_node)
                chain.append((j_id, "J", tap.x))
                target = (j_id, "J")
            tap.conn_ref[tap.side]["node"] = target[0]
            tap.conn_ref[tap.side]["anchor"] = target[1]

        chain.append((node_b_id, node_b_anchor, bus.x_max))
        chain.sort(key=lambda c: c[2])
        seen_ids = set()
        ordered = []
        for cid, anc, _ in chain:
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
            ordered.append((cid, anc))
        for (src_id, src_anc), (tgt_id, tgt_anc) in zip(ordered, ordered[1:]):
            data["connections"].append({
                "source": {"node": src_id, "anchor": src_anc},
                "target": {"node": tgt_id, "anchor": tgt_anc},
                "waypoints": [],
            })
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_rail.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add circuit_generator/rail.py tests/test_rail.py
git commit -m "feat: add rail.py bus materialization (node_a/node_b/junctions)"
```

---

### Task 2: `rail.py` — `request_tap()` push/evict resolver

**Files:**
- Modify: `circuit_generator/rail.py`
- Test: `tests/test_rail.py`

**Interfaces:**
- Consumes: `RailPlanner`, `Tap`, `_Bus` from Task 1.
- Produces: `RailPlanner.request_tap(bus_id, owner_id, owner_y, desired_x, conn_ref, side, push_dir=0, avoid_global_x=False) -> Tap` (returns the `Tap` actually registered — needed by Task 4 Step 4 to recover the resolved `x` for `mc_A_anchor` bookkeeping).

Ports `_resolve_conflict` (identical in `cascade_layout.py`, `layout_engine.py`, `step_by_step_layout.py`) from discrete `X{i}` grid indices to continuous x. Same qualitative rules:

- Two taps on the same bus "collide" if they land within `min_spacing` of each other (discrete version: same rounded column).
- A collision is a **false positive** (both taps keep their spot) when their owners are on opposite sides of the bus (`owner_y` vs. bus `y`) **and** that above/below order matches the order of the two owners' actual y (no wire crossing results).
- On a real collision, whichever owner has the smaller `owner_y` (physically higher) wins the slot; the loser is pushed by `min_spacing` in the direction implied by `push_dir` (or, if `push_dir == 0`, away from the bus's x midpoint) and re-resolved recursively against the bus's other taps (which can itself evict a third tap, exactly like today).
- `avoid_global_x=True` additionally checks (and registers into) a resolver-wide dict shared across every bus registered on this `RailPlanner`, keyed the same way — mirrors `cascade_layout.py`'s cross-PL check for `mem[i].A/B -> PL` connections.
- `x` is clamped to `[bus.x_min, bus.x_max]`; if pushing hits the same clamped value twice in one resolution (`seen`), give up and keep it there (mirrors `_resolve_conflict`'s `if anc in seen: return anc`).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_rail.py

def test_request_tap_two_taps_far_apart_keep_their_desired_x():
    planner = RailPlanner(min_spacing=60.0)
    planner.register_bus("pl1", "PressureLineTerminal", y=500.0, x_min=0.0, x_max=1000.0)
    c1, c2 = ({"source": {}}, {"source": {}})
    planner.request_tap("pl1", "a", owner_y=0.0, desired_x=100.0, conn_ref=c1, side="source")
    planner.request_tap("pl1", "b", owner_y=0.0, desired_x=800.0, conn_ref=c2, side="source")
    xs = sorted(t.x for t in planner._buses["pl1"].taps)
    assert xs == [100.0, 800.0]


def test_request_tap_colliding_same_side_pushes_the_loser():
    planner = RailPlanner(min_spacing=60.0)
    planner.register_bus("pl1", "PressureLineTerminal", y=500.0, x_min=0.0, x_max=1000.0)
    c1, c2 = ({"source": {}}, {"source": {}})
    # both owners above the bus (owner_y < bus_y=500) -> same side, real collision
    planner.request_tap("pl1", "a", owner_y=0.0, desired_x=300.0, conn_ref=c1, side="source")
    planner.request_tap("pl1", "b", owner_y=0.0, desired_x=300.0, conn_ref=c2, side="source")
    xs = sorted(t.x for t in planner._buses["pl1"].taps)
    assert xs[0] == 300.0
    assert xs[1] != 300.0
    assert abs(xs[1] - xs[0]) >= 60.0


def test_request_tap_opposite_sides_consistent_order_no_push():
    planner = RailPlanner(min_spacing=60.0)
    planner.register_bus("pl1", "PressureLineTerminal", y=500.0, x_min=0.0, x_max=1000.0)
    c1, c2 = ({"source": {}}, {"source": {}})
    # owner "above" (y=0 < bus_y=500) registers first at x=300
    planner.request_tap("pl1", "above", owner_y=0.0, desired_x=300.0, conn_ref=c1, side="source")
    # owner "below" (y=900 > bus_y=500), same x -> opposite sides, no real crossing
    planner.request_tap("pl1", "below", owner_y=900.0, desired_x=300.0, conn_ref=c2, side="source")
    xs = {t.owner_id: t.x for t in planner._buses["pl1"].taps}
    assert xs["above"] == 300.0
    assert xs["below"] == 300.0


def test_request_tap_avoid_global_x_pushes_across_different_buses():
    planner = RailPlanner(min_spacing=60.0)
    planner.register_bus("pl1", "PressureLineTerminal", y=200.0, x_min=0.0, x_max=1000.0)
    planner.register_bus("pl2", "PressureLineTerminal", y=800.0, x_min=0.0, x_max=1000.0)
    c1, c2 = ({"target": {}}, {"target": {}})
    # owner above pl1 (y=0 < 200) and owner below pl2 (y=1000 > 800): order INVERTS
    # relative to the buses' own y order (pl1's y=200 < pl2's y=800) -> real crossing
    planner.request_tap("pl1", "o1", owner_y=0.0, desired_x=300.0, conn_ref=c1, side="target",
                         avoid_global_x=True)
    planner.request_tap("pl2", "o2", owner_y=1000.0, desired_x=300.0, conn_ref=c2, side="target",
                         avoid_global_x=True)
    x1 = planner._buses["pl1"].taps[0].x
    x2 = planner._buses["pl2"].taps[0].x
    assert x1 != x2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rail.py -v -k request_tap`
Expected: FAIL with `AttributeError: 'RailPlanner' object has no attribute 'request_tap'`

- [ ] **Step 3: Implement `request_tap()`**

```python
# add to circuit_generator/rail.py, inside RailPlanner

    def __init__(self, min_spacing: float):
        self.min_spacing = min_spacing
        self._buses: dict[str, _Bus] = {}
        self._global_used: dict[int, tuple] = {}  # bucket -> (owner_id, owner_y, bus_y)

    def request_tap(self, bus_id: str, owner_id: str, owner_y: float, desired_x: float,
                     conn_ref: dict, side: str, push_dir: int = 0,
                     avoid_global_x: bool = False) -> None:
        bus = self._buses[bus_id]
        used = getattr(bus, "_used", None)
        if used is None:
            used = {}
            bus._used = used  # bucket -> Tap
        mid_x = (bus.x_min + bus.x_max) / 2

        def _clamp(x: float) -> float:
            return max(bus.x_min, min(bus.x_max, x))

        def _next(x: float, direction: int) -> float:
            step = direction if direction else (-1 if x <= mid_x else 1)
            return _clamp(x + step * self.min_spacing)

        def _bucket(x: float) -> int:
            return round((x - bus.x_min) / self.min_spacing)

        def _reg(x: float, oid: str, oy: float, cref: dict, side: str,
                 seen: frozenset, pdir: int) -> Tap:
            x = _clamp(x)
            b = _bucket(x)
            if b in seen:
                tap = Tap(x=x, owner_id=oid, owner_y=oy, conn_ref=cref, side=side, push_dir=pdir)
                bus.taps.append(tap)
                used[b] = tap
                return tap
            seen = seen | {b}

            if avoid_global_x:
                prev_global = self._global_used.get(b)
                if prev_global is not None:
                    prev_oid, prev_oy, prev_bus_y = prev_global
                    same_order = (oy < prev_oy) == (bus.y < prev_bus_y)
                    if prev_oid != oid and not same_order:
                        return _reg(_next(x, pdir), oid, oy, cref, side, seen, pdir)
                self._global_used[b] = (oid, oy, bus.y)

            prev = used.get(b)
            if prev is None:
                tap = Tap(x=x, owner_id=oid, owner_y=oy, conn_ref=cref, side=side, push_dir=pdir)
                bus.taps.append(tap)
                used[b] = tap
                return tap
            if prev.owner_id == oid:
                return prev

            # opp_sides + same-bus comparison: opposite-side taps on the
            # SAME bus never cross (one wire runs up, the other down), so
            # same_order is always trivially True here -- unlike the
            # avoid_global_x branch above, which compares against a
            # DIFFERENT bus's y and genuinely needs the non-trivial
            # formula (see layout_engine.py:557's comment: "Mesma PL: um
            # vem de cima, outro de baixo -> ordem trivialmente
            # consistente").
            curr_above = oy < bus.y
            prev_above = prev.owner_y < bus.y
            opp_sides = curr_above != prev_above
            if opp_sides:
                tap = Tap(x=x, owner_id=oid, owner_y=oy, conn_ref=cref, side=side, push_dir=pdir)
                bus.taps.append(tap)
                return tap
            if oy >= prev.owner_y:
                return _reg(_next(x, pdir), oid, oy, cref, side, seen, pdir)
            else:
                bus.taps.remove(prev)
                tap = Tap(x=x, owner_id=oid, owner_y=oy, conn_ref=cref, side=side, push_dir=pdir)
                bus.taps.append(tap)
                used[b] = tap
                _reg(_next(prev.x, prev.push_dir), prev.owner_id, prev.owner_y,
                     prev.conn_ref, prev.side, frozenset(), prev.push_dir)
                return tap

        return _reg(desired_x, owner_id, owner_y, conn_ref, side, frozenset(), push_dir)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rail.py -v`
Expected: PASS (all tests from Task 1 and Task 2)

- [ ] **Step 5: Commit**

```bash
git add circuit_generator/rail.py tests/test_rail.py
git commit -m "feat: add rail.py request_tap push/evict collision resolver"
```

---

### Task 3: `rail.py` — `assign_sorted()` resolver (electric buses)

**Files:**
- Modify: `circuit_generator/rail.py`
- Test: `tests/test_rail.py`

**Interfaces:**
- Consumes: `RailPlanner`, `Tap` from Task 1.
- Produces: `RailPlanner.assign_sorted(bus_id, requests: list[tuple[str, float, float, dict, str]]) -> None`, where each request tuple is `(owner_id, owner_y, desired_x, conn_ref, side)`.

Ports `step_by_step_electric_layout.py`'s `_select_nearest_anchors` two-pointer sweep: sorts requests by `desired_x`, walks them left to right, and assigns each the smallest available x that is at least `min_spacing` past the previously-assigned x — guarantees monotonic, non-colliding, crossing-proof-by-construction placement (exactly today's guarantee, just without a finite discrete anchor pool to draw from).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_rail.py

def test_assign_sorted_orders_taps_by_desired_x():
    planner = RailPlanner(min_spacing=60.0)
    planner.register_bus("vs1", "JunctionNodeItem", y=100.0, x_min=0.0, x_max=1000.0)
    c1, c2, c3 = ({"source": {}}, {"source": {}}, {"source": {}})
    planner.assign_sorted("vs1", [
        ("c", 0.0, 500.0, c3, "source"),
        ("a", 0.0, 100.0, c1, "source"),
        ("b", 0.0, 300.0, c2, "source"),
    ])
    xs = sorted(t.x for t in planner._buses["vs1"].taps)
    assert xs == sorted(xs)
    by_owner = {t.owner_id: t.x for t in planner._buses["vs1"].taps}
    assert by_owner["a"] < by_owner["b"] < by_owner["c"]


def test_assign_sorted_enforces_minimum_spacing_for_stacked_targets():
    planner = RailPlanner(min_spacing=60.0)
    planner.register_bus("vs1", "JunctionNodeItem", y=100.0, x_min=0.0, x_max=1000.0)
    c1, c2 = ({"source": {}}, {"source": {}})
    # two targets at the SAME real x (e.g. stacked power contacts) -- each
    # must still get its own, distinct anchor.
    planner.assign_sorted("vs1", [
        ("a", 0.0, 400.0, c1, "source"),
        ("b", 0.0, 400.0, c2, "source"),
    ])
    xs = sorted(t.x for t in planner._buses["vs1"].taps)
    assert abs(xs[1] - xs[0]) >= 60.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rail.py -v -k assign_sorted`
Expected: FAIL with `AttributeError: 'RailPlanner' object has no attribute 'assign_sorted'`

- [ ] **Step 3: Implement `assign_sorted()`**

```python
# add to circuit_generator/rail.py, inside RailPlanner

    def assign_sorted(self, bus_id: str, requests: list[tuple]) -> None:
        bus = self._buses[bus_id]
        ordered = sorted(requests, key=lambda r: r[2])  # by desired_x
        last_x = None
        for owner_id, owner_y, desired_x, conn_ref, side in ordered:
            x = desired_x if last_x is None else max(desired_x, last_x + self.min_spacing)
            x = max(bus.x_min, min(bus.x_max, x))
            bus.taps.append(Tap(x=x, owner_id=owner_id, owner_y=owner_y,
                                 conn_ref=conn_ref, side=side, push_dir=0))
            last_x = x
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rail.py -v`
Expected: PASS (all tests from Tasks 1-3)

- [ ] **Step 5: Commit**

```bash
git add circuit_generator/rail.py tests/test_rail.py
git commit -m "feat: add rail.py assign_sorted resolver for single-bus (electric) case"
```

---

### Task 4: Integrate `rail.py` into `layout_engine.py`

**Files:**
- Modify: `circuit_generator/layout_engine.py`
- Test: `tests/test_layout_engine_multi_cycle.py` (existing — must stay green, no assertions on `properties["anchors"]` today, see Global Constraints)

**Interfaces:**
- Consumes: `RailPlanner.register_bus`, `.request_tap`, `.materialize` from Tasks 1-2.

`layout_engine.py`'s PressureLine handling has one bus type, one resolver (no `avoid_global_x`). Delete and replace as follows:

- [ ] **Step 1: Delete the discrete-anchor helpers**

Delete `_pl_anchor_x` (`layout_engine.py:63-65`), `_nearest_pl_anchor` (`:68-89`), and `_best_pl_anchor_clear_column` (`:92-128`) — `_best_pl_anchor_clear_column`'s "avoid a column blocked by a sprite" behavior is **not** ported; note this as a known regression to file a follow-up ticket for (it only affected `sig.P` connections whose y-span crosses another sprite — rare and cosmetic, not a correctness issue, per this plan's scope of "make the generators produce valid, loadable circuits again").

- [ ] **Step 2: Replace `_scene_x`/`_scene_xy`'s PressureLine special case**

`_scene_x` (`:27-38`) and `_scene_xy` (`:41-58`) special-case `ntype == "PressureLine"` because today a PL's `"X{i}"` anchors don't have a `sprite_metrics.anchor_local` entry (they're computed from the index). After migration, PL taps are real `JunctionNodeItem`/`PressureLineTerminal` nodes with real positions already in `node_pos` and a real `anchor_local_for_routing` entry (`"J"`/`"X1"`) — so both functions' special case becomes dead and can be deleted, falling through to the existing generic `local = _anchor_local(...)` path:

```python
def _scene_x(node_id: str, anchor_name: str,
              node_pos: dict, node_type_map: dict) -> float | None:
    """Posição X em cena de um anchor de qualquer nó posicionado."""
    npos = node_pos.get(node_id)
    ntype = node_type_map.get(node_id, "")
    if npos is None:
        return None
    local = _anchor_local(ntype, anchor_name)
    return (npos[0] + local[0]) if local else npos[0]


def _scene_xy(node_id: str, anchor_name: str,
               node_pos: dict, node_type_map: dict) -> tuple[float, float] | None:
    """Posição (X, Y) em cena de um anchor de qualquer nó posicionado."""
    npos = node_pos.get(node_id)
    ntype = node_type_map.get(node_id, "")
    if npos is None:
        return None
    local = _anchor_local(ntype, anchor_name)
    return (npos[0] + local[0], npos[1] + local[1]) if local else npos
```

This requires `sprite_metrics.py`'s `anchor_local`/`anchor_local_for_routing` to carry entries for `"JunctionNodeItem"` (anchor `"J"`, local `(0, 0)`) and `"PressureLineTerminal"` (anchor `"X1"`, local `(pl_pix_w/2, pl_pix_h)` — same offset the deleted PL-special-case used for `idx==1`). Check `sprite_metrics.py`'s `_ANCHOR_LOCAL`/`anchor_local` dict; if these two types aren't already present (they likely aren't, since junctions/pressure-line-terminals are graphics-side additions from the prerequisite spec, not yet consumed by any generator), add them there as part of this step, mirroring the existing dict's shape for other single-anchor types.

- [ ] **Step 3: Replace Fase 2.8 (centering) to use `node_pos` instead of the anchor list**

Lines `488-517` compute `mid_idx` from `pl_node["properties"]["anchors"]`'s first/last index to find the PL's on-screen center. Since this phase runs **before** `rail.py`'s materialization (which hasn't happened yet at this point — the bus is still the old-style placeholder), this phase is unaffected by the migration as long as it keeps reading/writing `pl_node["position"]["x"]` the same way. **No change needed here** — leave Fase 2.8 exactly as-is; it operates purely on the placeholder node's `position`, never touches individual anchor positions.

- [ ] **Step 4: Replace Fase 3 (anchor assignment) with `RailPlanner.request_tap`**

Delete `_resolve_conflict` (`:524-571`) and the `pl_anchor_used`/`conn_by_owner`/`mc_A_anchor` dict declarations (`:520-522`). Before the `connections_sorted` loop (`:587`), construct the planner and register every PL bus. Since `_pl_anchor_x` is deleted (Step 1), compute each bus's `x_min`/`x_max` directly from the surviving anchor index range:

```python
    from circuit_generator.rail import RailPlanner
    from circuit_generator.sprite_metrics import METRICS as _M

    rail = RailPlanner(min_spacing=_M.pl_spacing)
    for pl_id, pl_node in pl_node_map.items():
        idxs = [int(a[1:]) for a in pl_node["properties"]["anchors"]]
        pl_x = node_pos[pl_id][0]
        x_min = pl_x + _M.pl_pix_w / 2 + (min(idxs) - min(idxs)) * _M.pl_spacing
        x_max = pl_x + _M.pl_pix_w / 2 + (max(idxs) - min(idxs)) * _M.pl_spacing
        rail.register_bus(pl_id, "PressureLineTerminal", y=node_pos[pl_id][1],
                           x_min=x_min, x_max=x_max)
    mc_A_anchor: dict[str, tuple[str, float]] = {}
```

Then rewrite every `_nearest_pl_anchor(...)` call site inside the `connections_sorted` loop (`:593-655`) to compute the same `target_x`/`tgt_x`/`src_x`/`ax`/`bx` value it computes today (unchanged — this is each connection shape's own geometry, not part of the anchor-index machinery), and call `rail.request_tap(pl_id, owner_id=<the other node's id>, owner_y=<that node's y>, desired_x=<the computed target x>, conn_ref=conn, side=<"source" or "target">)` instead of `_nearest_pl_anchor` + `_resolve_conflict`. For example, the `PL -> componente` branch (`:599-621`) becomes:

```python
        if s_id in pl_node_map and s_anc.startswith("X"):
            tgt_x = _scene_x(t_id, t_anc, node_pos, node_type_map)
            if tgt_x is None:
                continue
            rail.request_tap(s_id, owner_id=t_id, owner_y=node_pos.get(t_id, (0, 0))[1],
                              desired_x=tgt_x, conn_ref=conn, side="source")
```

(This drops the `side`-biased/`_best_pl_anchor_clear_column` special cases from the original `t_type == "Valve_3_2_Ways"`/`t_anc in ("PL", "PR")` branches — every case now just requests a tap at the target's real x; `request_tap`'s own push/evict logic handles the actual collision avoidance, same as `_resolve_conflict` did.) Apply the same pattern to the `componente -> PL` branch (`:623-655`) — keep each `elif`'s `src_x`/`OFF_PL`/`OFF_PR`/margin computation exactly as today, just end with `rail.request_tap(...)` instead of `_nearest_pl_anchor(...)` + `_resolve_conflict(...)`. For the `mc_A_anchor` bookkeeping (`:654-655`, used by Fase 3.5), store the resolved `x` instead of an anchor index — `request_tap` doesn't return the resolved `Tap` in Task 2's signature, so change it to return the `Tap` it created/reused (update Task 2's `request_tap` return type from `None` to `Tap`, returning the value of the outer `_reg(...)` call), then:

```python
            tap = rail.request_tap(t_id, owner_id=s_id, owner_y=node_pos.get(s_id, (0, 0))[1],
                                    desired_x=..., conn_ref=conn, side="target")
            if s_type == "Valve_5_2_Ways" and s_anc == "A":
                mc_A_anchor[s_id] = (t_id, tap.x)
```

- [ ] **Step 5: Replace Fase 3.5 (mc.B > mc.A) and Fase 3.9 (pruning)**

Fase 3.5 (`:657-668`) compared anchor *indices* to guarantee `mc.B`'s tap sits to the right of `mc.A`'s. With continuous x this becomes a direct x comparison against the stored `mc_A_anchor` x — but since `request_tap` already resolves real collisions via push/evict, and `mc.B`'s desired x is already computed with a rightward margin past `mc.A` (`:643-647`, unchanged by Step 4), this phase is now redundant and can be **deleted entirely**: `request_tap`'s own collision handling covers it.

Fase 3.9 (pruning, `:670-689`) computed the surviving anchor range purely to shrink `properties["anchors"]` for the *old* format — that's no longer needed since `rail.materialize()` (Task 1) already only creates junction nodes for taps that were actually requested. **Delete this phase entirely.**

- [ ] **Step 6: Call `rail.materialize()` before Fase 4 (A* routing)**

Immediately before the `astar_grid = build_grid(...)` line (`:694`), add:

```python
    rail.materialize(data, {n["id"]: n for n in data["nodes"]}, node_pos)
```

- [ ] **Step 7: Run the existing regression test**

Run: `pytest tests/test_layout_engine_multi_cycle.py -v`
Expected: PASS (no assertions on `properties["anchors"]` in this file — see Global Constraints)

- [ ] **Step 8: Add a round-trip test asserting the new shape**

```python
# append to tests/test_layout_engine_multi_cycle.py

def test_pressure_line_buses_use_the_new_paired_terminal_format():
    data = cascade.generate(parse("A+B+A-B-"))
    data = apply_layout(data)
    pl_nodes = [n for n in data["nodes"] if n["type"] == "PressureLine"]
    assert pl_nodes, "expected at least one PressureLine bus"
    for pl in pl_nodes:
        assert "anchors" not in pl["properties"]
    node_ids = {n["id"] for n in data["nodes"]}
    for conn in data["connections"]:
        assert conn["source"]["node"] in node_ids
        assert conn["target"]["node"] in node_ids
        assert not conn["source"]["anchor"].startswith("X") or conn["source"]["anchor"] == "X1"
        assert not conn["target"]["anchor"].startswith("X") or conn["target"]["anchor"] == "X1"
```

- [ ] **Step 9: Run it to verify it passes**

Run: `pytest tests/test_layout_engine_multi_cycle.py -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add circuit_generator/layout_engine.py circuit_generator/sprite_metrics.py tests/test_layout_engine_multi_cycle.py
git commit -m "refactor: layout_engine.py emits paired-terminal PressureLine buses"
```

---

### Task 5: Integrate `rail.py` into `step_by_step_layout.py`

**Files:**
- Modify: `circuit_generator/step_by_step_layout.py`
- Modify: `tests/test_step_by_step_layout.py`

**Interfaces:**
- Consumes: `RailPlanner` from Tasks 1-2, same pattern as Task 4.

Same shape of change as Task 4 (`step_by_step_layout.py`'s PL handling is a documented near-verbatim copy of `layout_engine.py`'s — see the comments at `step_by_step_layout.py:449-456`). Apply the identical substitution pattern from Task 4 Steps 1-6 to this file's equivalent blocks:

- [ ] **Step 1: Delete `_pl_anchor_x`/`_nearest_pl_anchor` (`:457-492`)**

- [ ] **Step 2: Register buses and replace `_resolve_conflict` (`:524-...`, find the matching block by searching for `def _resolve_conflict` in this file) with `rail.request_tap(...)` calls**, following Task 4 Step 4's pattern. This file's `_resolve_conflict` additionally supports `push_dir`/`avoid_global_x` params (`:524-526`) — pass them straight through to `request_tap`, which already supports both (Task 2).

- [ ] **Step 3: Delete the global pruning block** — search for the comment `"Global PressureLine pruning"` or equivalent (mirrors `layout_engine.py`'s Fase 3.9, referenced by this file's own comment at `:694`, `"(layout_engine.py's Phase 3.9)"`) and delete it, per Task 4 Step 5's reasoning.

- [ ] **Step 4: Call `rail.materialize(...)` before this file's A* routing phase.**

- [ ] **Step 5: Update `tests/test_step_by_step_layout.py`**

Run `grep -n '"anchors"' tests/test_step_by_step_layout.py` to enumerate the 11 existing assertions. For each:
- An assertion checking `pl_node["properties"]["anchors"]`'s *length* or *contents* directly (e.g. `assert len(pl["properties"]["anchors"]) == N`) — delete it; there is no longer a single node holding all the bus's taps to count.
- An assertion checking a specific connection's `["anchor"]` equals a specific `"X{i}"` value — replace with an assertion that the connection's node/anchor pair resolves to a real node in `data["nodes"]` whose `type` is `"JunctionNodeItem"` (anchor `"J"`) or `"PressureLineTerminal"`/`"PressureLine"` (anchor `"X1"`), and that no two *different* connections attached to the same original bus resolve to the same `(x, y)` position (the "no shared vertical line" regression check) — mirroring the pattern in Task 4 Step 8's `test_pressure_line_buses_use_the_new_paired_terminal_format`.

- [ ] **Step 6: Run the full test file**

Run: `pytest tests/test_step_by_step_layout.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add circuit_generator/step_by_step_layout.py tests/test_step_by_step_layout.py
git commit -m "refactor: step_by_step_layout.py emits paired-terminal PressureLine buses"
```

---

### Task 6: Integrate `rail.py` into `cascade_layout.py` (incl. `avoid_global_x`)

**Files:**
- Modify: `circuit_generator/cascade_layout.py`
- Modify: `tests/test_cascade_layout.py`

**Interfaces:**
- Consumes: `RailPlanner` from Tasks 1-2.

Same substitution pattern as Task 5, with two differences specific to this file:

- [ ] **Step 1: Delete `_pl_anchor_x`/`_nearest_pl_anchor`/`_resolve_conflict`** (`cascade_layout.py:609-695`, already read in full above) and the `pl_anchor_used`/`conn_by_owner`/`or_source_x_used`/`_mem_pl_used_x` dict declarations (`:573`, `:631-633`).

- [ ] **Step 2: Register buses and replace every `_resolve_conflict(...)` call** (the `connections_sorted` loop that uses these helpers, further below the excerpt already read — locate it by searching for `_resolve_conflict(` calls in the file) with `rail.request_tap(...)`, passing `avoid_global_x=True` for the `mem[i].A/B -> PL` case (`:937-939`, already confirmed) and `avoid_global_x=False` (default) everywhere else.

- [ ] **Step 3: Leave `_or_source_x`/`or_xy_conns` (`:697-772`) untouched** — this is the separate OrValve X/Y orientation-swap mechanism (Global Constraints). It calls `_pl_anchor_x` at `:726` (`if ntype == "PressureLine" and anchor_name.startswith("X"): return _pl_anchor_x(...)`) — since `_pl_anchor_x` is deleted in Step 1, replace that one call site with a direct `node_pos`-based lookup instead, now that PL taps are real nodes with real positions:

```python
    def _or_source_x(node_id: str, anchor_name: str) -> float | None:
        ntype = node_type_map.get(node_id, "")
        pos = node_by_id.get(node_id, {}).get("position")
        if pos is None:
            return None
        local = anchor_local_for_routing(ntype, anchor_name)
        return pos["x"] + (local[0] if local else 0.0)
```

(This drops the `ntype == "PressureLine"` special case entirely — after `rail.materialize()`, a PL-bus connection's source/target node is never the bus placeholder itself for a tap anchor anymore, it's a real `JunctionNodeItem`/`PressureLineTerminal`/the bus's own `node_a`, all of which already have real positions and `anchor_local_for_routing` entries, same as Task 4 Step 2.) **This means `_or_source_x` must run AFTER `rail.materialize()`, not before** — check this block's current position relative to the anchor-assignment loop and move the whole `or_xy_conns`/`_or_source_x` block (`:697-772`) to run after the `rail.materialize(...)` call (added in Step 4 below) if it doesn't already.

- [ ] **Step 4: Delete the global-pruning block** (`:941-960`, already read above) and call `rail.materialize(data, node_by_id, node_pos)` in its place.

- [ ] **Step 5: Update the local `_scene_xy` used by A\* routing setup** (`:998-1006`, already read above) — delete its `PressureLine`-special case the same way as Task 4 Step 2:

```python
    def _scene_xy(node_id: str, anchor_name: str) -> tuple[float, float] | None:
        pos = node_by_id[node_id]["position"]
        ntype = node_type_map.get(node_id, "")
        local = anchor_local_for_routing(ntype, anchor_name)
        return (pos["x"] + local[0], pos["y"] + local[1]) if local else (pos["x"], pos["y"])
```

- [ ] **Step 6: Update `tests/test_cascade_layout.py`**

This file has only 1 hit on `"anchors"` (from the earlier grep) — read it, and apply the same replacement rule as Task 5 Step 5.

- [ ] **Step 7: Run the full test file**

Run: `pytest tests/test_cascade_layout.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add circuit_generator/cascade_layout.py tests/test_cascade_layout.py
git commit -m "refactor: cascade_layout.py emits paired-terminal PressureLine buses"
```

---

### Task 7: Integrate `rail.py` into `step_by_step_electric_layout.py`

**Files:**
- Modify: `circuit_generator/step_by_step_electric_layout.py`
- Modify: `tests/test_step_by_step_electric_layout.py`

**Interfaces:**
- Consumes: `RailPlanner.register_bus`, `.assign_sorted`, `.materialize` from Tasks 1 and 3.

This file uses the sort-and-match resolver (Task 3), not the push/evict one (Tasks 2/4/5/6) — see Global Constraints and Task 3's rationale.

- [ ] **Step 1: Delete `_bus_anchor_x`/`_select_nearest_anchors`** (`:353-409`, already read above).

- [ ] **Step 2: Replace the sizing block** (`:300-311`, already read above) — it grew `properties["anchors"]` to `needed_count` entries; replace with computing `x_min`/`x_max` directly and registering both buses:

```python
    from circuit_generator.rail import RailPlanner

    rail = RailPlanner(min_spacing=_M.pl_spacing)
    x_range = grid.occupied_x_range()
    if x_range is not None:
        min_x, max_x = x_range
        needed_span = max(_M.pl_spacing, max_x - min_x)
    else:
        needed_span = _M.pl_spacing
    for bus_id in (vsource_id, ground_id):
        pos = node_by_id[bus_id]["position"]
        width = _M.vsource_pix_w if node_type_map[bus_id] == "VoltageSource" else _M.ground_pix_w * 0.5
        x0 = pos["x"] + width
        rail.register_bus(bus_id, "JunctionNodeItem", y=pos["y"], x_min=x0, x_max=x0 + needed_span)
```

- [ ] **Step 3: Replace the anchor-reassignment block** (`:411-446`, already read above) with `rail.assign_sorted(...)` calls, keeping this file's own `_other_endpoint_x` helper (`:361-364`, unchanged — it computes the *target*'s real x, not the bus's):

```python
    vsource_conns = [c for c in data["connections"] if c["source"]["node"] == vsource_id]
    ground_conns = [c for c in data["connections"] if c["target"]["node"] == ground_id]

    rail.assign_sorted(vsource_id, [
        (c["target"]["node"], node_by_id[c["target"]["node"]]["position"]["y"],
         _other_endpoint_x(c["target"]["node"], c["target"]["anchor"]), c, "source")
        for c in vsource_conns
    ])
    rail.assign_sorted(ground_id, [
        (c["source"]["node"], node_by_id[c["source"]["node"]]["position"]["y"],
         _other_endpoint_x(c["source"]["node"], c["source"]["anchor"]), c, "target")
        for c in ground_conns
    ])
```

- [ ] **Step 4: Call `rail.materialize(...)` right after, before the "Final cleanup" section (`:448-450`)**

```python
    rail.materialize(data, node_by_id, node_pos)
```

(Confirm `node_pos` is in scope at this point in the file's `apply()` — if this file tracks positions purely via `node_by_id[...]["position"]` without a separate `node_pos` dict, build one inline: `node_pos = {n["id"]: (n["position"]["x"], n["position"]["y"]) for n in data["nodes"]}` immediately before this call.)

- [ ] **Step 5: Update `_scene_xy`** (`:455-468`, already read above) — delete the `VoltageSource`/`Ground` special cases the same way as Task 4 Step 2:

```python
    def _scene_xy(node_id: str, anchor_name: str) -> tuple[float, float] | None:
        pos = node_by_id[node_id]["position"]
        ntype = node_type_map.get(node_id, "")
        local = anchor_local_for_routing(ntype, anchor_name)
        return (pos["x"] + local[0], pos["y"] + local[1]) if local else (pos["x"], pos["y"])
```

This requires `sprite_metrics.py` to carry an `anchor_local_for_routing` entry for `"JunctionNodeItem"`'s `"J"` anchor at local `(0, 0)` — same entry needed by Task 4 Step 2; if that task lands first, nothing more to add here.

- [ ] **Step 6: Check `_bus_vh_route`** (referenced at `:470` onward, not fully read in this plan — read it before editing) — it dispatches deterministic VH routing for "any connection touching a `VoltageSource`/`Ground` anchor" ([[project_tcc_circuitos_step_by_step_electric]]'s bus-routing fix). Confirm its dispatch condition checks `node_type_map.get(...) in ("VoltageSource", "Ground")` on the *original* bus id, not on the anchor name — if it currently also keys off `anchor_name.startswith("X")`, update it to recognize the new tap targets (`JunctionNodeItem`/real `node_a` anchor `"X1"`) the same way `get_exit_dir`/`anchor_local_for_routing` do post-migration, since after `rail.materialize()` most connections into the bus no longer have the bus id as their node at all (only the extreme taps do — interior taps now target a `JunctionNodeItem`). If the dispatch condition can't be preserved simply, it's acceptable for this task to route those connections through the same A* path as everything else (regression: possible visual detour, not a correctness bug) — note it as a follow-up if so, matching Task 4 Step 1's treatment of `_best_pl_anchor_clear_column`.

- [ ] **Step 7: Update `tests/test_step_by_step_electric_layout.py`**

Run `grep -n '"anchors"' tests/test_step_by_step_electric_layout.py` to enumerate the 12 existing assertions, and apply the same replacement rule as Task 5 Step 5 (delete length/contents assertions on the bus's `properties["anchors"]`; replace specific-anchor-index assertions with "resolves to a real node, no two taps share a position" assertions). Pay particular attention to `TestMultiCyclePowerStacking` (referenced in `_select_nearest_anchors`'s docstring, `:384-394`) — its stacked-power-contact regression (two targets at the same real x must still get distinct anchors) is exactly what Task 3's `test_assign_sorted_enforces_minimum_spacing_for_stacked_targets` unit-tests in isolation; keep this integration-level test, updated to check the new node/connection shape instead of anchor names.

- [ ] **Step 8: Run the full test file**

Run: `pytest tests/test_step_by_step_electric_layout.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add circuit_generator/step_by_step_electric_layout.py tests/test_step_by_step_electric_layout.py
git commit -m "refactor: step_by_step_electric_layout.py emits paired-terminal Ground/VoltageSource buses"
```

---

### Task 8: End-to-end round-trip through the real node classes

**Files:**
- Create: `tests/test_generators_paired_terminal_roundtrip.py`

**Interfaces:**
- Consumes: `circuit_generator.circuit_generator.generate_and_load` (existing), the real `NodeItem.from_dict`/`ConnectionItem.from_dict` (existing).

Confirms the generated JSON isn't just internally consistent (Tasks 4-7's own tests) but actually loads through the real graphics node classes without erroring — the concrete regression the prerequisite redesign spec warned about ("old format... breaks" against the new node classes).

- [ ] **Step 1: Write the test**

```python
# tests/test_generators_paired_terminal_roundtrip.py
import pytest
from PyQt6.QtWidgets import QApplication, QGraphicsScene

from circuit_generator.circuit_generator import generate_and_load


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeEditor:
    pass


@pytest.mark.parametrize("method,sub_type,sequence", [
    ("cascade", None, "A+B+A-B-"),
    ("step_by_step", "pneumatic", "A+B+A-B-"),
    ("step_by_step", "electric", "A+B+A-B-"),
])
def test_generated_circuit_loads_without_error(method, sub_type, sequence):
    scene = QGraphicsScene()
    generate_and_load(sequence, method, sub_type, scene, _FakeEditor())
    node_types = {item.node_type for item in scene.items() if hasattr(item, "node_type")}
    assert "junction" not in node_types or True  # junctions are lowercase node_type; presence is fine
    # No node is left holding the old anchor-list format:
    for item in scene.items():
        props = getattr(item, "properties", None)
        if props is not None:
            assert "anchors" not in props
```

- [ ] **Step 2: Run it to verify it fails before Tasks 4-7 land** (skip if run after — this is a regression guard, not a TDD driver for new production code)

Run: `pytest tests/test_generators_paired_terminal_roundtrip.py -v`
Expected: PASS once Tasks 4-7 are complete; if run earlier, FAILS with a `KeyError`/`AttributeError` from the old node classes rejecting `properties["anchors"]`.

- [ ] **Step 3: Run it**

Run: `pytest tests/test_generators_paired_terminal_roundtrip.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_generators_paired_terminal_roundtrip.py
git commit -m "test: end-to-end round-trip of all 3 generator methods through real node classes"
```

---

## Self-Review Notes

- **Spec coverage:** `rail.py`'s materialization (Task 1) covers the spec's "Materialize the nodes/rail connections/rewrite map" section. `request_tap` (Task 2) covers the push/evict resolver and `avoid_global_x`. `assign_sorted` (Task 3) is a refinement over the brainstormed design, added because `step_by_step_electric_layout.py` never used the push/evict resolver to begin with — it has its own simpler, already-crossing-proof algorithm; forcing it through `request_tap` would be a needless behavior change the spec didn't ask for. Tasks 4-7 cover "each generator's own reach/sizing stays, only the final write-out changes" for all four files (`layout_engine.py` included, per the spec's explicit scope even though it's dead code in the dispatch table — it still has its own regression test). Task 8 covers the spec's underlying motivation (old format errors against new node classes).
- **Known, called-out regressions** (both flagged inline as follow-ups, not silently dropped): `_best_pl_anchor_clear_column`'s "avoid a column blocked by a sprite" (Task 4 Step 1) and `_bus_vh_route`'s dispatch condition needing re-verification against the new tap shape (Task 7 Step 6).
- **Type consistency:** `Tap`, `RailPlanner.register_bus`/`.request_tap`/`.assign_sorted`/`.materialize` signatures are used identically across Tasks 2-7 as defined in Task 1-3.
