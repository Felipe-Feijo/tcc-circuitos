"""Fluxo de criação de junção em CONNECT: anchor->linha e linha->anchor,
undo de uma tacada só, e cancelamento (clicar em vazio) desfazendo o
split -- não deve sobrar uma JunctionNodeItem órfã se o usuário desistir
no meio do gesto."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsObject
from PyQt6.QtCore import QPointF, QPoint, QRectF

app = QApplication.instance() or QApplication([])

from editor.editor_state import EditorState
from editor.mode import EditorMode
from graphics.anchors.anchor import AnchorItem
from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.junction_node_item import JunctionNodeItem
from graphics.items.base.nodes.node_item import NodeItem
from graphics.view import GraphicsView
from simulation.nodes.nodes import Junction


class _DummyNode(NodeItem):
    """Nó mínimo p/ testes. Precisa ser um NodeItem de verdade (não só um
    QGraphicsObject qualquer) -- o teste de cancelamento
    (test_cancel_after_split_rolls_back_completely) exercita o rollback
    real via editor.undo._restore_snapshot, que passa pela cena inteira
    por persistence.serializer.serialize_scene/deserialize_scene; esse
    serializer só reconhece isinstance(item, NodeItem), então um node de
    teste que não seja NodeItem faz o snapshot "antes" sair vazio e o
    rollback apagar a cena inteira em vez de só desfazer o split."""
    node_type = "dummy_test_node"
    simulation_cls = Junction

    def setup(self) -> None:
        self.width = 0.0
        self.height = 0.0
        # Todas as direções por padrão -- o teste narrowa via
        # set_exit_directions() depois da construção (ver make_node); um
        # round-trip de serialização (deserialize_scene) recria o node do
        # zero via setup(), então o default aqui não pode ser uma lista
        # vazia (_choose_best_exit_direction quebra com allowed_dirs=[]).
        all_dirs = ["right", "left", "top", "bottom"]
        self.add_anchor(AnchorItem(
            "P", QPointF(0, 0), node=self, domain=self.domain,
            exit_directions={"external": list(all_dirs), "internal": list(all_dirs)},
        ))


class _FakeEvent:
    """Substitui QMouseEvent nos testes -- handle_connect_press/
    _complete_connect_press só chamam .pos(), nunca .button() (o botão já
    foi checado por mousePressEvent antes de despachar pra eles)."""

    def __init__(self, view_pos: QPoint):
        self._pos = view_pos

    def pos(self) -> QPoint:
        return self._pos


def _event_at(view: GraphicsView, scene_pos: QPointF) -> _FakeEvent:
    """QGraphicsView.mapFromScene(QPointF) já retorna QPoint (não
    QPointF) -- sem conversão extra."""
    return _FakeEvent(view.mapFromScene(scene_pos))


def make_node(scene, x, y, name, exit_dirs, domain="pneumatic"):
    node = _DummyNode(domain=domain)
    node.setPos(x, y)
    scene.addItem(node)
    anchor = node.anchors.pop("P")
    anchor.name = name
    anchor.id = (node.id, name)
    anchor.set_exit_directions({"external": exit_dirs, "internal": exit_dirs})
    node.anchor_list = [anchor]
    node.anchors = {name: anchor}
    return node


def make_view(scene, editor):
    view = GraphicsView(editor)
    view.setScene(scene)
    editor.mode = EditorMode.CONNECT
    return view


def test_split_connection_at_creates_junction_and_two_children():
    scene = QGraphicsScene()
    editor = EditorState()
    view = make_view(scene, editor)

    node_a = make_node(scene, 0, 0, "P", ["right"])
    node_b = make_node(scene, 100, 0, "P", ["left"])
    conn = ConnectionItem(node_a, node_a.anchors["P"], node_b, node_b.anchors["P"])
    conn.editor = editor
    scene.addItem(conn)
    node_a.connections.append(conn)
    node_b.connections.append(conn)
    conn.get_path_points()

    j_anchor = view.split_connection_at(conn, QPointF(50, 0))

    assert j_anchor is not None
    assert isinstance(j_anchor.node, JunctionNodeItem)
    assert len(j_anchor.node.connections) == 2

    # A remoção da conexão original (prepare_delete()+removeItem()) é
    # adiada via QTimer.singleShot(0, ...) -- mesmo padrão de
    # DeleteManager/NodeItem.remove_anchor -- pra evitar mexer no índice
    # espacial da cena de forma síncrona dentro de mousePressEvent. Só
    # depois do event loop processar é que ela some de fato.
    app.processEvents()

    assert conn.scene() is None  # a conexão original foi removida
    assert len(node_a.connections) == 1
    assert node_a.connections[0] is not conn
    assert len(node_b.connections) == 1
    assert node_b.connections[0] is not conn


def test_anchor_to_line_flow_creates_three_way_junction_with_dot():
    scene = QGraphicsScene()
    editor = EditorState()
    view = make_view(scene, editor)

    node_a = make_node(scene, 0, 0, "P", ["right"])
    node_b = make_node(scene, 100, 0, "P", ["left"])
    conn = ConnectionItem(node_a, node_a.anchors["P"], node_b, node_b.anchors["P"])
    conn.editor = editor
    scene.addItem(conn)
    node_a.connections.append(conn)
    node_b.connections.append(conn)
    conn.get_path_points()

    node_c = make_node(scene, 50, 100, "P", ["top"])

    # 1º clique: anchor de origem = node_c.
    editor.hover_anchor = node_c.anchors["P"]
    view.handle_connect_press(_event_at(view, node_c.pos()))
    assert editor._connecting is True

    # 2º clique: solta em cima da linha da conexão original (não há
    # hover_anchor -- é isso que aciona o fallback de split).
    editor.hover_anchor = None
    target_scene_pos = QPointF(50, 0)
    view._complete_connect_press(_event_at(view, target_scene_pos))

    junction_anchors = [n.anchors["J"] for n in scene.items() if isinstance(n, JunctionNodeItem)]
    assert len(junction_anchors) == 1
    j_anchor = junction_anchors[0]
    assert j_anchor.connection_count() == 3
    assert j_anchor.brush().color().alpha() > 0  # bolinha visível
    assert editor._connecting is False

    # Flush da remoção adiada da conexão original do split (QTimer.singleShot),
    # pra não deixar um timer pendente vazando pro próximo teste do módulo.
    app.processEvents()


def test_cancel_after_split_rolls_back_completely():
    scene = QGraphicsScene()
    editor = EditorState()
    view = make_view(scene, editor)

    node_a = make_node(scene, 0, 0, "P", ["right"])
    node_b = make_node(scene, 100, 0, "P", ["left"])
    conn = ConnectionItem(node_a, node_a.anchors["P"], node_b, node_b.anchors["P"])
    conn.editor = editor
    scene.addItem(conn)
    node_a.connections.append(conn)
    node_b.connections.append(conn)
    conn.get_path_points()

    before_node_count = len(scene.items())

    # 1º clique: linha->anchor -- começa a conexão a partir de um split.
    editor.hover_anchor = None
    view.handle_connect_press(_event_at(view, QPointF(50, 0)))
    assert editor._connecting is True
    assert len(scene.items()) > before_node_count  # split já aconteceu

    # Em uso real, o event loop roda entre dois cliques de mouse distintos
    # -- o que dá tempo do QTimer.singleShot(0, ...) da remoção adiada da
    # conexão original (ver split_connection_at) disparar e assentar ANTES
    # do segundo clique. Sem isso aqui, o rollback abaixo (_restore_snapshot
    # -> deserialize_scene(clear_scene=True) -> scene.clear()) deletaria o
    # objeto C++ da conexão original ainda pendente de remoção, e o timer
    # adiado explodiria com RuntimeError ao disparar mais tarde (inclusive
    # possivelmente durante processEvents() de um teste totalmente diferente).
    app.processEvents()

    # 2º clique: em vazio, sem hover_anchor nem conexão sob o cursor --
    # cancela o gesto inteiro.
    editor.hover_anchor = None
    view._complete_connect_press(_event_at(view, QPointF(-500, -500)))

    assert editor._connecting is False
    remaining_junctions = [n for n in scene.items() if isinstance(n, JunctionNodeItem)]
    assert remaining_junctions == []
    remaining_conns = [i for i in scene.items() if isinstance(i, ConnectionItem)]
    assert len(remaining_conns) == 1
    assert remaining_conns[0].source_anchor.name == "P"
