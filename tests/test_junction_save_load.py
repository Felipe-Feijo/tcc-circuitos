# tests/test_junction_save_load.py
"""Round-trip completo: uma cena com fonte -> junção -> (terra, ramo
morto) precisa sobreviver a serialize_scene/deserialize_scene sem nenhum
código de persistência dedicado -- só o class_registry genérico de
NodeItem."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.scene import GraphicsScene
from persistence.serializer import serialize_scene, deserialize_scene
from graphics.items.base.nodes.junction_node_item import JunctionNodeItem
from graphics.items.base.connections.connection_item import ConnectionItem


def _state_with_junction() -> dict:
    return {
        "version": 1,
        "nodes": [
            {"id": "src", "type": "JunctionNodeItem", "domain": "electric",
             "position": {"x": 0.0, "y": 0.0}, "rotation": 0.0,
             "properties": {}, "labels": {}, "anchor_labels": {}},
            {"id": "gnd", "type": "JunctionNodeItem", "domain": "electric",
             "position": {"x": 100.0, "y": 0.0}, "rotation": 0.0,
             "properties": {}, "labels": {}, "anchor_labels": {}},
            {"id": "dead", "type": "JunctionNodeItem", "domain": "electric",
             "position": {"x": 50.0, "y": 100.0}, "rotation": 0.0,
             "properties": {}, "labels": {}, "anchor_labels": {}},
            {"id": "junction", "type": "JunctionNodeItem", "domain": "electric",
             "position": {"x": 50.0, "y": 0.0}, "rotation": 0.0,
             "properties": {}, "labels": {}, "anchor_labels": {}},
        ],
        "connections": [
            {"source": {"node": "src", "anchor": "J"}, "target": {"node": "junction", "anchor": "J"}},
            {"source": {"node": "junction", "anchor": "J"}, "target": {"node": "gnd", "anchor": "J"}},
            {"source": {"node": "junction", "anchor": "J"}, "target": {"node": "dead", "anchor": "J"}},
        ],
    }


def test_junction_survives_round_trip():
    scene = GraphicsScene()
    items = deserialize_scene(_state_with_junction(), scene, editor=None)

    junction_item = next(i for i in items if getattr(i, "id", None) == "junction")
    assert isinstance(junction_item, JunctionNodeItem)
    assert junction_item.anchors["J"].connection_count() == 3
    assert junction_item.anchors["J"].brush().color().alpha() > 0  # bolinha visível

    reserialized = serialize_scene(scene)
    node_types = {n["id"]: n["type"] for n in reserialized["nodes"]}
    assert node_types["junction"] == "JunctionNodeItem"
    assert len(reserialized["connections"]) == 3

    scene._test_ref = scene  # mantém viva até o fim do teste (ver padrão em test_connection_boundary_conflict.py)
