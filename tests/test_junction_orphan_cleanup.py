"""Uma JunctionNodeItem tem boundingRect()/shape() 0x0 (sem corpo visível
por design) -- se ambos os ramos dela forem deletados um de cada vez (não
os dois juntos), ela vira um nó órfão de 0 conexões inclicável/
inselecionável/indeletável pela UI normal, mas continua sendo serializado
em todo save futuro para sempre. ConnectionItem.prepare_delete() precisa
detectar essa condição (anchor.connection_count() caiu pra 0 num anchor
cujo node é uma JunctionNodeItem) e remover o node órfão também, pelo
mesmo padrão adiado (QTimer.singleShot(0, ...)) usado em
split_connection_at/DeleteManager -- ver
tests/test_node_item_remove_anchor_defers_scene_removal.py."""
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
    tests/test_view_connection_junction.py."""
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


def test_orphan_junction_removed_after_last_branch_deleted():
    scene = QGraphicsScene()

    source = _make_leaf(scene, 0, 0)
    ground = _make_leaf(scene, 100, 0)
    dead   = _make_leaf(scene, 50, 100)

    junction = JunctionNodeItem(domain="electric")
    junction.setPos(50, 0)
    scene.addItem(junction)
    j_anchor = junction.anchors["J"]

    conn_source = ConnectionItem(source, source.anchors["P"], junction, j_anchor)
    conn_ground = ConnectionItem(junction, j_anchor, ground, ground.anchors["P"])
    conn_dead   = ConnectionItem(junction, j_anchor, dead, dead.anchors["P"])
    for conn in (conn_source, conn_ground, conn_dead):
        scene.addItem(conn)
    source.connections.append(conn_source)
    junction.connections.extend([conn_source, conn_ground, conn_dead])
    ground.connections.append(conn_ground)
    dead.connections.append(conn_dead)

    assert j_anchor.connection_count() == 3
    assert junction.scene() is scene

    # Deleta o primeiro ramo: junction ainda tem 2 conexões -- não deve
    # ser removida (esse caso intermediário já é coberto por outros
    # testes; aqui só confirmamos que não dispara cedo demais).
    conn_ground.prepare_delete()
    scene.removeItem(conn_ground)
    app.processEvents()

    assert j_anchor.connection_count() == 2
    assert junction.scene() is scene

    # Deleta o segundo ramo: junction cai pra 1 conexão -- ainda viva.
    conn_dead.prepare_delete()
    scene.removeItem(conn_dead)
    app.processEvents()

    assert j_anchor.connection_count() == 1
    assert junction.scene() is scene

    # Deleta o último ramo: junction cai pra 0 conexões -- o node órfão
    # precisa ser removido da cena também, via QTimer.singleShot(0, ...).
    conn_source.prepare_delete()
    scene.removeItem(conn_source)

    # Antes do event loop processar, a remoção do node ainda está pendente
    # (mesma garantia de atomicidade adiada que o resto do codebase usa).
    assert junction.scene() is scene

    app.processEvents()

    assert junction.scene() is None
    assert j_anchor.connection_count() == 0
