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
        self._global_used: dict[int, tuple] = {}  # bucket -> (owner_id, owner_y, bus_y)

    def register_bus(self, bus_id: str, node_b_type: str, y: float,
                      x_min: float, x_max: float) -> None:
        self._buses[bus_id] = _Bus(node_b_type=node_b_type, y=y, x_min=x_min, x_max=x_max)

    def request_tap(self, bus_id: str, owner_id: str, owner_y: float, desired_x: float,
                     conn_ref: dict, side: str, push_dir: int = 0,
                     avoid_global_x: bool = False) -> Tap:
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

        # When bus has zero taps, node_b is at x_min + min_spacing; otherwise at x_max
        node_b_x = bus.x_min + self.min_spacing if not bus.taps else bus.x_max

        node_b_id = f"{bus_id}-b-{uuid.uuid4().hex[:8]}"
        node_b = {
            "id": node_b_id, "type": bus.node_b_type, "domain": domain,
            "position": {"x": node_b_x, "y": bus.y},
            "properties": {},
        }
        node_by_id[node_b_id] = node_b
        node_pos[node_b_id] = (node_b_x, bus.y)
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

        chain.append((node_b_id, node_b_anchor, node_b_x))
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
