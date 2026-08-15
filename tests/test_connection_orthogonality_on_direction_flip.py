"""Reprodução: arrastar um node cujo anchor aceita as 4 direções (hoje só
JunctionNodeItem) pode fazer _choose_best_exit_direction() trocar de eixo
(ex.: de "right" pra "top") entre um movimento e o próximo -- dx/dy
cruzam de dominância. adjust_waypoints_for_node_move()/_adjust_boundary()
foram desenhados assumindo que o eixo travado (exit_h/entry_h) permanece
estável entre chamadas; quando ele muda de identidade, o "fast path sem
conflito" (snap só do waypoint da borda, sem tocar no vizinho interno)
pode deixar o waypoint da borda alinhado com a NOVA âncora num eixo, mas
seu OUTRO eixo continua obsoleto (alinhado com a âncora ANTIGA) -- o
segmento borda->vizinho vira diagonal."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsObject
from PyQt6.QtCore import QPointF, QRectF

app = QApplication.instance() or QApplication([])

from graphics.anchors.anchor import AnchorItem
from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.junction_node_item import JunctionNodeItem
from graphics.items.base.nodes.node_item import NodeItem
from simulation.nodes.nodes import Junction

_ALL_DIRS = ["right", "left", "top", "bottom"]


class _FixedLeaf(QGraphicsObject):
    """Nó com direção de saída FIXA (só "right") -- mantém o lado do
    node fixo como variável de controle, isolando a instabilidade no
    lado da junção (que aceita as 4 direções)."""
    _next_id = 0

    def __init__(self, x, y):
        super().__init__()
        _FixedLeaf._next_id += 1
        self.id = f"leaf-{_FixedLeaf._next_id}"
        self.connections = []
        self.editor = None
        self.setPos(x, y)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, 1, 1)

    def paint(self, painter, option, widget=None):
        pass


def _make_leaf(scene, x, y):
    leaf = _FixedLeaf(x, y)
    scene.addItem(leaf)
    anchor = AnchorItem("P", QPointF(0, 0), node=leaf, domain="electric",
                         exit_directions={"external": ["right"], "internal": ["right"]})
    anchor.setParentItem(leaf)
    leaf.anchor_list = [anchor]
    leaf.anchors = {"P": anchor}
    return leaf


def _assert_orthogonal(points, context: str):
    for a, b in zip(points, points[1:]):
        same_x = abs(a.x() - b.x()) < 0.5
        same_y = abs(a.y() - b.y()) < 0.5
        assert same_x or same_y, (
            f"{context}: segmento diagonal entre {(a.x(), a.y())} e "
            f"{(b.x(), b.y())} -- nem x nem y batem"
        )


def test_connection_stays_orthogonal_when_junction_move_flips_exit_axis():
    scene = QGraphicsScene()
    leaf = _make_leaf(scene, 0, 0)

    junction = JunctionNodeItem(domain="electric")
    junction.setPos(100, 5)  # dx domina -> entry_dir horizontal ("left")
    scene.addItem(junction)
    j_anchor = junction.anchors["J"]

    conn = ConnectionItem(leaf, leaf.anchors["P"], junction, j_anchor)
    scene.addItem(conn)
    leaf.connections.append(conn)
    junction.connections.append(conn)

    initial_points = conn.get_path_points()
    _assert_orthogonal(initial_points, "rota inicial")

    # Move a junção pra uma posição onde dy passa a dominar dx -- o
    # entry_dir ideal vira vertical ("top"), trocando a identidade do
    # eixo travado no meio do caminho.
    junction.setPos(5, 100)
    conn.adjust_waypoints_for_node_move(moved_source=False, moved_target=True)

    points_after_flip = conn.get_path_points()
    _assert_orthogonal(points_after_flip, "rota após a troca de eixo")
