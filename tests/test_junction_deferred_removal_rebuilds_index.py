"""Reprodução do crash real relatado pelo usuário: "Windows fatal
exception: access violation" em GraphicsView._connection_at, chamado de
mouseMoveEvent em modo CONNECT, minutos depois de um split/merge de
junção.

Causa raiz: as remoções adiadas via QTimer.singleShot(0, ...) (padrão já
estabelecido em DeleteManager.do_delete/NodeItem.remove_anchor pra evitar
o MESMO crash) removiam os itens da cena mas nunca reconstruíam o índice
espacial (BSP) depois -- só metade da mitigação. O índice ficava com
entradas obsoletas que corrompiam uma query espacial subsequente
(scene().items(pos), exatamente o que _connection_at faz a cada
mouseMoveEvent). ConnectionItem._rebuild_scene_index() precisa rodar
depois de TODA remoção adiada de item de conexão/junção -- este teste
prova que ela realmente roda em cada um dos três caminhos que fazem esse
tipo de remoção, usando uma QGraphicsScene que conta chamadas a
invalidate() (marcador específico da dança de reconstrução) em vez de
tentar mockar métodos nativos do Qt (unittest.mock.patch em método de
QGraphicsScene já causou access violation numa tentativa anterior nesta
suíte -- subclassear e sobrescrever é seguro, substituir o bound method
não é)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene
from PyQt6.QtCore import QPointF

app = QApplication.instance() or QApplication([])

from editor.editor_state import EditorState
from editor.mode import EditorMode
from graphics.anchors.anchor import AnchorItem
from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.junction_node_item import JunctionNodeItem
from graphics.items.base.nodes.node_item import NodeItem
from graphics.view import GraphicsView
from simulation.nodes.nodes import Junction

_ALL_DIRS = ["right", "left", "top", "bottom"]


class _TrackedScene(QGraphicsScene):
    """Conta chamadas a invalidate() -- marcador da dança de reconstrução
    do índice espacial (mesmo padrão de DeleteManager.do_delete). Uma
    subclasse real do Qt, não um mock substituindo o método -- seguro."""

    def __init__(self):
        super().__init__()
        self.invalidate_calls = 0

    def invalidate(self, *args, **kwargs):
        self.invalidate_calls += 1
        super().invalidate(*args, **kwargs)


class _DummyNode(NodeItem):
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


def test_split_connection_at_rebuilds_scene_index():
    scene = _TrackedScene()
    editor = EditorState()
    editor.mode = EditorMode.CONNECT
    view = GraphicsView(editor)
    view.setScene(scene)

    source = _make_leaf(scene, 0, 0)
    ground = _make_leaf(scene, 100, 0)
    conn = ConnectionItem(source, source.anchors["P"], ground, ground.anchors["P"])
    conn.editor = editor
    scene.addItem(conn)
    source.connections.append(conn)
    ground.connections.append(conn)
    conn.get_path_points()

    view.split_connection_at(conn, QPointF(50, 0))
    assert scene.invalidate_calls == 0  # ainda não rodou -- adiado

    app.processEvents()

    assert scene.invalidate_calls >= 1


def test_merge_on_collapse_rebuilds_scene_index():
    scene = _TrackedScene()

    source = _make_leaf(scene, 0, 0)
    ground = _make_leaf(scene, 200, 0)
    dead   = _make_leaf(scene, 100, 100)

    junction = JunctionNodeItem(domain="electric")
    junction.setPos(100, 0)
    scene.addItem(junction)
    j_anchor = junction.anchors["J"]

    conn_source = ConnectionItem(source, source.anchors["P"], junction, j_anchor)
    conn_ground = ConnectionItem(junction, j_anchor, ground, ground.anchors["P"])
    conn_dead   = ConnectionItem(junction, j_anchor, dead, dead.anchors["P"])
    for c in (conn_source, conn_ground, conn_dead):
        scene.addItem(c)
    source.connections.append(conn_source)
    junction.connections.extend([conn_source, conn_ground, conn_dead])
    ground.connections.append(conn_ground)
    dead.connections.append(conn_dead)

    conn_dead.prepare_delete()
    scene.removeItem(conn_dead)
    assert scene.invalidate_calls == 0  # merge ainda não rodou -- adiado

    app.processEvents()

    assert scene.invalidate_calls >= 1


def test_orphan_cleanup_rebuilds_scene_index():
    scene = _TrackedScene()

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

    conn_ground.prepare_delete()
    scene.removeItem(conn_ground)
    app.processEvents()
    scene.invalidate_calls = 0  # reseta -- só quer medir a próxima remoção

    conn_source.prepare_delete()
    scene.removeItem(conn_source)
    assert scene.invalidate_calls == 0  # limpeza do órfão ainda não rodou

    app.processEvents()

    assert scene.invalidate_calls >= 1
