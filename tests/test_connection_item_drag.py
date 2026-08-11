import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsObject
from PyQt6.QtCore import QPointF, QRectF, Qt

app = QApplication.instance() or QApplication([])

from graphics.anchors.anchor import AnchorItem
from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.diagram_item_base import DiagramItemBase


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


class FakeMouseEvent:
    """Substituto mínimo de QGraphicsSceneMouseEvent (PyQt6 não permite
    instanciar diretamente) -- só o suficiente pra exercitar mousePress/Move/
    ReleaseEvent de ConnectionItem."""

    def __init__(self, x: float, y: float, button=Qt.MouseButton.LeftButton):
        self._pos = QPointF(x, y)
        self._button = button
        self.accepted = False

    def scenePos(self) -> QPointF:
        return self._pos

    def button(self):
        return self._button

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.accepted = False


def test_dragging_first_waypoint_keeps_boundary_segment_orthogonal():
    scene = QGraphicsScene()
    node_a = make_node(scene, 0, 0, ["right"])
    node_b = make_node(scene, 200, 50, ["left"])
    conn = make_connection(scene, node_a, node_b)
    conn.get_path_points()  # inicializa a rota padrão (2 waypoints, hvh)

    wp0 = conn.waypoints[0]
    conn.mousePressEvent(FakeMouseEvent(wp0.x(), wp0.y()))
    assert conn._drag_mode == 'waypoint'

    # Arrasta o waypoint de ponta bem longe, num ponto que não é nem a
    # mesma x nem a mesma y do estado original -- é essa liberdade de
    # movimento que expunha a diagonal.
    conn.mouseMoveEvent(FakeMouseEvent(wp0.x() + 40, wp0.y() + 40))
    # DiagramItemBase.mouseReleaseEvent chama super().mouseReleaseEvent(event),
    # que é um método C++ (via sip) e exige um QGraphicsSceneMouseEvent real --
    # tipo que o PyQt6 não permite instanciar (daí o FakeMouseEvent). Sem
    # acesso a um QGraphicsSceneMouseEvent de verdade, isolamos essa chamada
    # de framework pra poder exercitar a lógica de reset de drag do
    # ConnectionItem sem o TypeError do sip.
    with patch.object(DiagramItemBase, 'mouseReleaseEvent', lambda self, event: None):
        conn.mouseReleaseEvent(FakeMouseEvent(wp0.x() + 40, wp0.y() + 40))

    p1_out, _ = conn._resolved_points()[0], None
    p1_out = conn._resolved_points()[0][0]
    new_wp0 = conn.waypoints[0]
    same_x = abs(p1_out.x() - new_wp0.x()) < 0.5
    same_y = abs(p1_out.y() - new_wp0.y()) < 0.5
    assert same_x or same_y, (
        f"segmento p1_out->waypoints[0] não é ortogonal: {p1_out} -> {new_wp0}"
    )
