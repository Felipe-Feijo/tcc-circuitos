"""Reprodução: conexões e labels carregados de um arquivo salvo não
seguiam o toggle de tema.

Causa raiz #1 (conexões): deserialize_scene() setava node.editor antes de
scene.addItem(node), mas nunca conn.editor antes de scene.addItem(conn) --
assimetria entre os dois loops. Sem .editor, o item nunca conecta em
EditorState.theme_changed (guard `if self.editor and ...` em itemChange),
então self.use_light_theme fica travado em False pra sempre.

Causa raiz #2 (labels): LabelItem nunca teve nenhum código que reagisse a
theme_changed -- a cor era fixada uma vez em __init__ e nunca mais tocada,
mesmo para nodes desenhados na cena (não só carregados de arquivo)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from editor.editor_state import EditorState
from graphics.scene import GraphicsScene
from persistence.serializer import deserialize_scene
from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.check_valve.check_valve import CheckValve


def _state() -> dict:
    return {
        "version": 1,
        "nodes": [
            {"id": "a", "type": "CheckValve", "domain": "hydraulic",
             "position": {"x": 0.0, "y": 0.0}, "rotation": 0.0,
             "properties": {"piloted": False}, "labels": {}, "anchor_labels": {}},
            {"id": "b", "type": "CheckValve", "domain": "hydraulic",
             "position": {"x": 300.0, "y": 0.0}, "rotation": 0.0,
             "properties": {"piloted": False}, "labels": {}, "anchor_labels": {}},
        ],
        "connections": [
            {"source": {"node": "a", "anchor": "Y"},
             "target": {"node": "b", "anchor": "X"},
             "waypoints": []},
        ],
    }


def test_connection_loaded_from_file_reacts_to_theme_toggle():
    editor = EditorState()
    scene = GraphicsScene()
    items = deserialize_scene(_state(), scene, editor=editor)
    conn = next(i for i in items if isinstance(i, ConnectionItem))
    conn._test_scene_ref = scene  # mantém a QGraphicsScene C++ viva

    assert conn.editor is editor
    assert conn.use_light_theme is False

    editor.theme_changed.emit(True)

    assert conn.use_light_theme is True


def test_node_label_follows_theme_toggle():
    from graphics.labels.label import LabelItem

    editor = EditorState()
    scene = GraphicsScene()
    node = CheckValve(domain="hydraulic")
    node.editor = editor
    scene.addItem(node)
    node.add_label("custom", LabelItem(properties={"text": "X", "editable": True, "movable": True}))
    label = node.labels["custom"]
    label._test_scene_ref = scene

    assert label.properties["color"] == Qt.GlobalColor.white

    editor.theme_changed.emit(True)

    assert label.properties["color"] == Qt.GlobalColor.black
    assert label.defaultTextColor() == Qt.GlobalColor.black
