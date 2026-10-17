import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.pilot_operated_relief_valve import PilotOperatedReliefValve
from simulation.graph_builder import GraphBuilder
from simulation.nodes.pilot_operated_relief_valve import PilotOperatedReliefValve as Node


def make_item(**props):
    item = PilotOperatedReliefValve(domain="hydraulic")
    item.properties.update(props)
    return item


def test_node_type_and_simulation_cls():
    assert PilotOperatedReliefValve.node_type == "pilot_operated_relief_valve"
    assert PilotOperatedReliefValve.simulation_cls is Node


def test_palette_meta():
    meta = PilotOperatedReliefValve.palette_meta()
    assert meta.domains == ("hydraulic",)
    assert meta.name == "Relief Valve (pilot-operated)"
    assert meta.sprite.endswith("pilot_operated_relief_valve.png")


def test_sprite_size():
    item = make_item()
    assert (item.width, item.height) == (254, 161)


def test_anchor_positions_and_exits():
    item = make_item()
    w, h = item.width, item.height
    assert set(item.anchors) == {"P", "T", "X"}
    pos = {n: (a.pos().x(), a.pos().y()) for n, a in item.anchors.items()}
    assert pos["P"] == (w * 98.5 / 254, 0)
    assert pos["T"] == (w * 98.5 / 254, h)
    assert pos["X"] == (w, h * 19.5 / 161)
    assert item.anchors["P"].exit_directions == {"external": ["top"]}
    assert item.anchors["T"].exit_directions == {"external": ["bottom"]}
    assert item.anchors["X"].exit_directions == {"external": ["right"]}


def test_plug_overlay_follows_x_connection():
    item = make_item()
    x = item.anchors["X"]
    repaints = []
    item.update = lambda *a, **k: repaints.append(1)

    assert item.x_plugged() is True

    conn = SimpleNamespace(source_anchor=x, target_anchor=None)
    item.connections.append(conn)
    x.refresh_junction_dot()
    assert item.x_plugged() is False
    assert repaints

    item.connections.remove(conn)
    repaints.clear()
    x.refresh_junction_dot()
    assert item.x_plugged() is True
    assert repaints


def test_connection_on_other_port_keeps_plug():
    item = make_item()
    item.connections.append(SimpleNamespace(source_anchor=item.anchors["P"], target_anchor=None))
    assert item.x_plugged() is True


def test_dialog_prefilled():
    item = make_item(p_set=1e7, p_vent=4e5)
    dialog = item.build_properties_dialog()
    assert float(dialog._field_p_set.text()) == 1e7
    assert float(dialog._field_p_vent.text()) == 4e5


def test_apply_dialog_sets_both_properties():
    item = make_item()
    dialog = item.build_properties_dialog()
    dialog._field_p_set.setText("1.2e7")
    dialog._field_p_vent.setText("5e5")
    item.apply_properties_from_dialog(dialog)
    assert item.properties["p_set"] == 1.2e7
    assert item.properties["p_vent"] == 5e5


def test_apply_dialog_empty_p_vent_removes_property():
    item = make_item(p_set=1e7, p_vent=5e5)
    dialog = item.build_properties_dialog()
    dialog._field_p_vent.setText("")
    item.apply_properties_from_dialog(dialog)
    assert "p_vent" not in item.properties
    node = Node("po", domain="hydraulic", properties=item.properties)
    assert node.p_vent == Node.DEFAULT_P_VENT


def test_json_round_trip_with_p_vent():
    item = make_item(p_set=1e7, p_vent=4e5)
    loaded = NodeItem.from_dict(item.to_dict())
    assert isinstance(loaded, PilotOperatedReliefValve)
    assert loaded.properties == {"p_set": 1e7, "p_vent": 4e5}
    assert set(loaded.anchors) == {"P", "T", "X"}


def test_json_round_trip_without_p_vent():
    item = make_item(p_set=1e7)
    loaded = NodeItem.from_dict(item.to_dict())
    assert "p_vent" not in loaded.properties
    assert Node("po", domain="hydraulic", properties=loaded.properties).p_vent == 3e5


def test_graph_builder_accepts_unconnected_x():
    item = make_item(p_set=1e7)
    builder = GraphBuilder()
    node = builder.add_node_from_item(item)
    builder.raise_if_errors()  # unconnected X must not be a validation error
    assert set(node.anchors) == {"P", "T", "X"}
