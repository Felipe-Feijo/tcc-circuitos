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
