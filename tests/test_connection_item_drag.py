import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsObject
from PyQt6.QtCore import QPointF, QRectF, Qt

app = QApplication.instance() or QApplication([])

from graphics.anchors.anchor import AnchorItem
from graphics.items.base.connections.connection_item import ConnectionItem


class _DummyNode(QGraphicsObject):
    """Nó mínimo o bastante para hospedar uma AnchorItem em testes de
    ConnectionItem -- não desenha nada, só existe pra dar posição/id/scene."""

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


def make_node(scene: QGraphicsScene, x: float, y: float, exit_dirs: list) -> _DummyNode:
    """Cria um node com uma única âncora 'P' na origem local, com as
    exit_directions dadas (usadas tanto pra 'external' quanto 'internal',
    já que os testes aqui nunca conectam dois anchors do mesmo node)."""
    node = _DummyNode(x, y)
    scene.addItem(node)
    anchor = AnchorItem(
        name="P", pos=QPointF(0, 0), node=node, domain="pneumatic",
        exit_directions={"external": exit_dirs, "internal": exit_dirs},
    )
    anchor.setParentItem(node)
    node.anchor_list = [anchor]
    return node


def make_connection(scene: QGraphicsScene, node_a, node_b, waypoints=None) -> ConnectionItem:
    conn = ConnectionItem(node_a, node_a.anchor_list[0], node_b, node_b.anchor_list[0])
    if waypoints is not None:
        conn.waypoints = [QPointF(x, y) for x, y in waypoints]
        conn._waypoints_initialized = True
    scene.addItem(conn)
    node_a.connections.append(conn)
    node_b.connections.append(conn)
    return conn


def test_resolved_points_wraps_waypoints_with_anchor_margins():
    scene = QGraphicsScene()
    node_a = make_node(scene, 0, 0, ["right"])
    node_b = make_node(scene, 200, 50, ["left"])
    conn = make_connection(scene, node_a, node_b)

    # Força a inicialização da rota padrão (get_path_points faz isso na
    # primeira chamada).
    conn.get_path_points()

    points, anchored = conn._resolved_points()

    assert len(points) == len(conn.waypoints) + 2
    assert anchored == frozenset({0, len(points) - 1})
    # O primeiro/último ponto resolvido é o ponto de margem, não o anchor cru.
    assert points[0] != node_a.anchor_list[0].scenePos()
    assert points[-1] != node_b.anchor_list[0].scenePos()
