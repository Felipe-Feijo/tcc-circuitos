"""compute_split_point() localiza o ponto mais próximo sobre a rota
roteada (não a linha reta ponto-a-ponto) de uma ConnectionItem, e divide
os waypoints existentes em duas metades -- usado por
GraphicsView.split_connection_at() pra criar uma JunctionNodeItem no meio
de um fio."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsObject
from PyQt6.QtCore import QPointF, QRectF

app = QApplication.instance() or QApplication([])

from graphics.anchors.anchor import AnchorItem
from graphics.items.base.connections.connection_item import ConnectionItem


class _DummyNode(QGraphicsObject):
    _next_id = 0

    def __init__(self, x, y):
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
    anchor = AnchorItem("P", QPointF(0, 0), node=node, domain="pneumatic",
                         exit_directions={"external": exit_dirs, "internal": exit_dirs})
    anchor.setParentItem(node)
    node.anchor_list = [anchor]
    return node


def test_split_point_on_straight_two_point_route():
    scene = QGraphicsScene()
    node_a = make_node(scene, 0, 0, ["right"])
    node_b = make_node(scene, 100, 0, ["left"])
    conn = ConnectionItem(node_a, node_a.anchor_list[0], node_b, node_b.anchor_list[0])
    scene.addItem(conn)
    conn.get_path_points()  # força o roteamento inicial (popula self.waypoints)

    result = conn.compute_split_point(QPointF(50, 0))
    assert result is not None
    point, wp_before, wp_after = result
    assert abs(point.y()) < 1.0
    assert 30 < point.x() < 70
    assert wp_before == []
    assert wp_after == []


def test_split_point_none_far_from_route():
    scene = QGraphicsScene()
    node_a = make_node(scene, 0, 0, ["right"])
    node_b = make_node(scene, 100, 0, ["left"])
    conn = ConnectionItem(node_a, node_a.anchor_list[0], node_b, node_b.anchor_list[0])
    scene.addItem(conn)
    conn.get_path_points()

    assert conn.compute_split_point(QPointF(50, 500)) is None


def test_split_point_partitions_existing_waypoints():
    scene = QGraphicsScene()
    node_a = make_node(scene, 0, 0, ["right"])
    node_b = make_node(scene, 100, 0, ["left"])
    conn = ConnectionItem(node_a, node_a.anchor_list[0], node_b, node_b.anchor_list[0])
    conn.waypoints = [QPointF(20, 0), QPointF(20, 50), QPointF(80, 50), QPointF(80, 0)]
    conn._waypoints_initialized = True
    scene.addItem(conn)

    # Clica no segmento horizontal do meio (y=50, entre x=20 e x=80).
    result = conn.compute_split_point(QPointF(50, 50))
    assert result is not None
    point, wp_before, wp_after = result
    assert abs(point.y() - 50) < 1.0
    assert wp_before == [QPointF(20, 0), QPointF(20, 50)]
    assert wp_after == [QPointF(80, 50), QPointF(80, 0)]


def test_prepare_delete_refreshes_junction_dot_on_both_anchors():
    """Reprodução do caso de colapso: um anchor com 3 conexões (bolinha
    visível) que perde uma delas via prepare_delete() (o que DeleteManager
    chama antes de remover o item da cena) precisa recalcular a bolinha
    na hora -- não só na próxima vez que algo mexer no anchor."""
    scene = QGraphicsScene()
    node_a = make_node(scene, 0, 0, ["right"])
    node_b = make_node(scene, 100, 0, ["left"])
    node_c = make_node(scene, 50, 100, ["top"])

    conn_ab = ConnectionItem(node_a, node_a.anchor_list[0], node_b, node_b.anchor_list[0])
    conn_ac = ConnectionItem(node_a, node_a.anchor_list[0], node_c, node_c.anchor_list[0])
    scene.addItem(conn_ab)
    scene.addItem(conn_ac)
    node_a.connections = [conn_ab, conn_ac]
    node_b.connections = [conn_ab]
    node_c.connections = [conn_ac]

    anchor_a = node_a.anchor_list[0]
    anchor_a.refresh_junction_dot()
    assert anchor_a.connection_count() == 2
    assert anchor_a.brush().color().alpha() == 0  # só 2 -- ainda sem bolinha

    # Uma terceira conexão no mesmo anchor liga a bolinha...
    node_d = make_node(scene, -50, 50, ["left"])
    conn_ad = ConnectionItem(node_a, node_a.anchor_list[0], node_d, node_d.anchor_list[0])
    scene.addItem(conn_ad)
    node_a.connections.append(conn_ad)
    node_d.connections = [conn_ad]
    anchor_a.refresh_junction_dot()
    assert anchor_a.brush().color().alpha() > 0

    # ...e prepare_delete() de UMA das três deve apagá-la de novo, sem
    # nenhuma chamada extra do teste.
    conn_ad.prepare_delete()
    assert anchor_a.connection_count() == 2
    assert anchor_a.brush().color().alpha() == 0
