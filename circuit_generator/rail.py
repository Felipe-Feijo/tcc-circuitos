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
