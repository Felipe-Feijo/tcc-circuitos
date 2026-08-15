"""JunctionNodeItem precisa ser arrastável: boundingRect()/shape() 0x0
deixava o Qt incapaz de acertar o item no hit test, mesmo com
ItemIsMovable=True já herdado de NodeItem.__init__ e o reroteamento de
conexões ao mover um node já sendo 100% genérico (NodeItem.itemChange ->
update_connections()). Este teste prova que mover uma JunctionNodeItem
reroteia as conexões ligadas a ela, exatamente como qualquer outro node."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene
from PyQt6.QtCore import QPointF

app = QApplication.instance() or QApplication([])

from graphics.anchors.anchor import AnchorItem
from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.junction_node_item import JunctionNodeItem
from graphics.items.base.nodes.node_item import NodeItem
from simulation.nodes.nodes import Junction

_ALL_DIRS = ["right", "left", "top", "bottom"]


class _DummyNode(NodeItem):
    """Nó mínimo de teste com um único anchor "P" -- mesmo padrão usado em
    tests/test_junction_orphan_cleanup.py."""
    node_type = "dummy_test_node"
    simulation_cls = Junction

    def setup(self) -> None:
        self.width = 0.0
        self.height = 0.0
        self.add_anchor(AnchorItem(
            "P", QPointF(0, 0), node=self, domain=self.domain,
            exit_directions={"external": list(_ALL_DIRS), "internal": list(_ALL_DIRS)},
        ))


def _make_leaf(scene, x, y, domain="electric"):
    node = _DummyNode(domain=domain)
    node.setPos(x, y)
    scene.addItem(node)
    return node


def test_junction_node_item_flags_are_selectable_and_movable():
    """Confirma que os flags de Qt (herdados de DiagramItemBase/NodeItem)
    estão ligados -- o bloqueio real era só a geometria vazia, não os
    flags, que já vinham corretos desde sempre."""
    from PyQt6.QtWidgets import QGraphicsItem

    item = JunctionNodeItem(domain="electric")
    assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
    assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable


def test_moving_junction_reroutes_its_connections():
    scene = QGraphicsScene()

    source = _make_leaf(scene, 0, 0)
    ground = _make_leaf(scene, 100, 0)

    junction = JunctionNodeItem(domain="electric")
    junction.setPos(50, 0)
    scene.addItem(junction)
    j_anchor = junction.anchors["J"]

    conn_source = ConnectionItem(source, source.anchors["P"], junction, j_anchor)
    conn_ground = ConnectionItem(junction, j_anchor, ground, ground.anchors["P"])
    scene.addItem(conn_source)
    scene.addItem(conn_ground)
    source.connections.append(conn_source)
    junction.connections.extend([conn_source, conn_ground])
    ground.connections.append(conn_ground)

    # Força o roteamento inicial (popula waypoints) antes de mover, do
    # mesmo jeito que a cena real faria ao desenhar pela primeira vez.
    conn_source.get_path_points()
    conn_ground.get_path_points()

    # Arrastar a junção é só um setPos() -- é exatamente o que
    # QGraphicsItem faz internamente durante um mouseMoveEvent de drag
    # real; testar via setPos() direto exercita o mesmo itemChange() que
    # um arrasto de mouse dispararia, sem a fragilidade de sintetizar
    # QMouseEvents reais (ver padrão em tests/test_connection_item_drag.py).
    junction.setPos(50, 40)

    assert j_anchor.scenePos() == QPointF(50, 40)

    # As duas conexões precisam ter recalculado a rota a partir da nova
    # posição -- get_path_points() já reflete isso porque
    # update_connections() chamou adjust_waypoints_for_node_move().
    points_source = conn_source.get_path_points()
    points_ground = conn_ground.get_path_points()
    assert points_source[-1] == QPointF(50, 40)
    assert points_ground[0] == QPointF(50, 40)


def test_junction_still_selectable_and_draggable_with_only_two_connections():
    """Mesmo sem a bolinha visível (só aparece com 3+ conexões), a junção
    continua arrastável -- não há necessidade de esconder a geometria de
    hit test em função da contagem de conexões."""
    scene = QGraphicsScene()

    source = _make_leaf(scene, 0, 0)
    ground = _make_leaf(scene, 100, 0)

    junction = JunctionNodeItem(domain="electric")
    junction.setPos(50, 0)
    scene.addItem(junction)
    j_anchor = junction.anchors["J"]

    conn_source = ConnectionItem(source, source.anchors["P"], junction, j_anchor)
    conn_ground = ConnectionItem(junction, j_anchor, ground, ground.anchors["P"])
    scene.addItem(conn_source)
    scene.addItem(conn_ground)
    source.connections.append(conn_source)
    junction.connections.extend([conn_source, conn_ground])
    ground.connections.append(conn_ground)

    assert j_anchor.connection_count() == 2
    assert j_anchor.brush().color().alpha() == 0  # sem bolinha, mas...
    assert not junction.boundingRect().isEmpty()  # ...ainda arrastável
