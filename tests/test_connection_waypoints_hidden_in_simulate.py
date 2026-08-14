"""Regressão: os diamonds de waypoint continuavam sendo desenhados durante
a simulação (EditorMode.SIMULATE) se a conexão estivesse selecionada/hovered
de antes de entrar no modo -- edição está desabilitada em SIMULATE, então os
handles (que só servem pra arrastar/editar a rota) não deveriam aparecer.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsObject
from PyQt6.QtCore import QPointF, QRectF

app = QApplication.instance() or QApplication([])

from editor.editor_state import EditorState
from editor.mode import EditorMode
from graphics.anchors.anchor import AnchorItem
from graphics.items.base.connections.connection_item import ConnectionItem


class _DummyNode(QGraphicsObject):
    _next_id = 0

    def __init__(self, x: float, y: float):
        super().__init__()
        _DummyNode._next_id += 1
        self.id = f"node-{_DummyNode._next_id}"
        self.connections = []
        self.editor = None
        self.setPos(x, y)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, 1, 1)

    def paint(self, painter, option, widget=None):
        pass


def make_node(scene, x, y, exit_dirs):
    node = _DummyNode(x, y)
    scene.addItem(node)
    anchor = AnchorItem(
        name="P", pos=QPointF(0, 0), node=node, domain="pneumatic",
        exit_directions={"external": exit_dirs, "internal": exit_dirs},
    )
    anchor.setParentItem(node)
    node.anchor_list = [anchor]
    return node


def make_connection(scene, node_a, node_b, waypoints):
    conn = ConnectionItem(node_a, node_a.anchor_list[0], node_b, node_b.anchor_list[0])
    conn.waypoints = [QPointF(x, y) for x, y in waypoints]
    conn._waypoints_initialized = True
    scene.addItem(conn)
    node_a.connections.append(conn)
    node_b.connections.append(conn)
    return conn


def test_waypoint_handles_drawn_in_select_mode_when_selected():
    scene = QGraphicsScene()
    node_a = make_node(scene, 0, 0, ["right"])
    node_b = make_node(scene, 100, 0, ["left"])
    conn = make_connection(scene, node_a, node_b, [(50, 0)])
    conn.editor = EditorState()
    conn.editor.mode = EditorMode.SELECT
    conn._selected_wp = 0

    painter = MagicMock()
    conn._draw_waypoint_handles(painter)
    assert painter.drawPath.called


def test_waypoint_handles_hidden_in_simulate_mode_even_when_selected():
    scene = QGraphicsScene()
    node_a = make_node(scene, 0, 0, ["right"])
    node_b = make_node(scene, 100, 0, ["left"])
    conn = make_connection(scene, node_a, node_b, [(50, 0)])
    conn.editor = EditorState()
    conn.editor.mode = EditorMode.SIMULATE
    # Estado que, em SELECT, faria o handle aparecer (selecionado + hovered).
    conn._selected_wp = 0
    conn._hovered_wp = 0

    painter = MagicMock()
    conn._draw_waypoint_handles(painter)
    assert not painter.drawPath.called
