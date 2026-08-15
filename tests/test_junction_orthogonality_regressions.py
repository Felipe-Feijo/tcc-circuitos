"""Reprodução de dois bugs reais reportados pelo usuário, mesma causa
raiz: waypoints herdados de OUTRA conexão (split de linha ou merge ao
colapsar uma junção) foram calculados sob as margens/direção de saída da
conexão de ORIGEM -- não necessariamente as mesmas que a conexão NOVA
calcula pra si, já que o anchor "J" de uma JunctionNodeItem aceita as 4
direções (JunctionNodeItem.setup). Sem re-ancorar, o segmento perto do
ponto de junção pode sair diagonal já na criação, antes de qualquer
arrasto -- e piora a cada movimento subsequente.

Corrigido com ConnectionItem.reanchor_waypoints(), chamado logo após
construir conn_a/conn_b em GraphicsView.split_connection_at e `merged` em
ConnectionItem._merge_junction_if_collapsed.

Terceiro bug, real e MUITO mais fácil de disparar (reportado pelo usuário
com screenshot depois dos dois primeiros já corrigidos): uma conexão sem
waypoint NENHUM (o caso mais comum -- qualquer split feito exatamente
sobre um trecho reto nasce assim) ficava completamente desprotegida em
`adjust_waypoints_for_node_move()` -- o guard de entrada descartava a
chamada inteira quando `self.waypoints` estava vazio, então mover a
junção pra qualquer posição fora do eixo original virava uma diagonal
reta sem NENHUM bridge sendo inserido. Corrigido tratando o caso de 0
waypoints explicitamente: reroteia do zero se p1_out/p2_in deixaram de
compartilhar eixo (não há nada pra preservar num trecho sem waypoint
próprio)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsObject
from PyQt6.QtCore import QPointF, QRectF

app = QApplication.instance() or QApplication([])

from editor.editor_state import EditorState
from editor.mode import EditorMode
from graphics.anchors.anchor import AnchorItem
from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.junction_node_item import JunctionNodeItem
from graphics.view import GraphicsView


class _Leaf(QGraphicsObject):
    _next_id = 0

    def __init__(self, x, y):
        super().__init__()
        _Leaf._next_id += 1
        self.id = f"leaf-{_Leaf._next_id}"
        self.connections = []
        self.editor = None
        self.setPos(x, y)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, 1, 1)

    def paint(self, painter, option, widget=None):
        pass


def _make_leaf(scene, x, y, dirs):
    leaf = _Leaf(x, y)
    scene.addItem(leaf)
    anchor = AnchorItem("P", QPointF(0, 0), node=leaf, domain="electric",
                         exit_directions={"external": dirs, "internal": dirs})
    anchor.setParentItem(leaf)
    leaf.anchors = {"P": anchor}
    return leaf


def _assert_orthogonal(points, context: str):
    for a, b in zip(points, points[1:]):
        same_x = abs(a.x() - b.x()) < 0.5
        same_y = abs(a.y() - b.y()) < 0.5
        assert same_x or same_y, (
            f"{context}: segmento diagonal entre {(a.x(), a.y())} e "
            f"{(b.x(), b.y())}"
        )


def test_moving_junction_off_axis_from_a_zero_waypoint_split_stays_orthogonal():
    """Reprodução exata do bug reportado com screenshot: split feito
    exatamente sobre um trecho reto (0 waypoints nas duas metades -- o
    caso mais comum), depois arrasta a junção pra fora do eixo original.
    Sem a correção, os dois segmentos que tocam a junção viravam retas
    diagonais (sem NENHUM bridge inserido), porque
    adjust_waypoints_for_node_move() descartava a chamada inteira quando
    self.waypoints estava vazio."""
    scene = QGraphicsScene()
    editor = EditorState()
    editor.mode = EditorMode.CONNECT
    view = GraphicsView(editor)
    view.setScene(scene)

    a = _make_leaf(scene, 0, 0, ["right"])
    b = _make_leaf(scene, 200, 0, ["left"])
    conn = ConnectionItem(a, a.anchors["P"], b, b.anchors["P"])
    conn.editor = editor
    scene.addItem(conn)
    a.connections.append(conn)
    b.connections.append(conn)
    conn.get_path_points()
    assert conn.waypoints == []  # confirma que a rota original é reta

    j_anchor = view.split_connection_at(conn, QPointF(100, 0))
    app.processEvents()
    junction = j_anchor.node

    children = [c for c in scene.items() if isinstance(c, ConnectionItem)]
    assert len(children) == 2
    assert all(c.waypoints == [] for c in children)  # confirma 0 waypoints nas duas metades

    junction.setPos(100, 80)

    for c in children:
        _assert_orthogonal(c.get_path_points(), "após mover junção de split reto pra fora do eixo")


def test_split_at_off_grid_point_stays_orthogonal():
    """Split num ponto que não é exatamente um waypoint existente --
    reprodução exata do bug real: source(0,0)->target(200,200) roteado em
    Z, split em (100,100) (fora dos waypoints da rota original,
    (100,0)/(100,200))."""
    scene = QGraphicsScene()
    editor = EditorState()
    editor.mode = EditorMode.CONNECT
    view = GraphicsView(editor)
    view.setScene(scene)

    a = _make_leaf(scene, 0, 0, ["right"])
    b = _make_leaf(scene, 200, 200, ["left"])
    conn = ConnectionItem(a, a.anchors["P"], b, b.anchors["P"])
    conn.editor = editor
    scene.addItem(conn)
    a.connections.append(conn)
    b.connections.append(conn)
    conn.get_path_points()

    j_anchor = view.split_connection_at(conn, QPointF(100, 100))
    app.processEvents()

    children = [c for c in scene.items() if isinstance(c, ConnectionItem)]
    assert len(children) == 2
    for c in children:
        _assert_orthogonal(c.get_path_points(), "logo após o split")


def test_connection_stays_orthogonal_across_multiple_junction_drags():
    """Mesmo split, depois duas arrastadas consecutivas da junção pra
    posições que fariam a direção "ideal" trocar de eixo -- cada uma
    precisa continuar ortogonal, não só a primeira."""
    scene = QGraphicsScene()
    editor = EditorState()
    editor.mode = EditorMode.CONNECT
    view = GraphicsView(editor)
    view.setScene(scene)

    a = _make_leaf(scene, 0, 0, ["right"])
    b = _make_leaf(scene, 200, 200, ["left"])
    conn = ConnectionItem(a, a.anchors["P"], b, b.anchors["P"])
    conn.editor = editor
    scene.addItem(conn)
    a.connections.append(conn)
    b.connections.append(conn)
    conn.get_path_points()

    j_anchor = view.split_connection_at(conn, QPointF(100, 100))
    app.processEvents()
    junction = j_anchor.node
    children = [c for c in scene.items() if isinstance(c, ConnectionItem)]

    for new_pos in [(150, 20), (10, 190), (5, 5), (195, 195)]:
        junction.setPos(*new_pos)
        for c in children:
            if c.scene():
                _assert_orthogonal(c.get_path_points(), f"após mover pra {new_pos}")


def test_merge_after_off_grid_split_stays_orthogonal_and_reasonably_shaped():
    """Fluxo completo: split num ponto fora da rota original, adiciona um
    terceiro ramo (dead-end), depois deleta esse ramo (colapsa pra 2 ->
    merge). O resultado tem que ficar ortogonal E manter uma forma
    razoável (não vira uma reta arbitrária nem perde a orientação geral
    original)."""
    scene = QGraphicsScene()
    editor = EditorState()
    editor.mode = EditorMode.CONNECT
    view = GraphicsView(editor)
    view.setScene(scene)

    a = _make_leaf(scene, 0, 0, ["right"])
    b = _make_leaf(scene, 200, 200, ["left"])
    conn = ConnectionItem(a, a.anchors["P"], b, b.anchors["P"])
    conn.editor = editor
    scene.addItem(conn)
    a.connections.append(conn)
    b.connections.append(conn)
    conn.get_path_points()

    j_anchor = view.split_connection_at(conn, QPointF(100, 100))
    app.processEvents()
    junction = j_anchor.node

    dead = _make_leaf(scene, 100, 300, ["top"])
    conn_dead = ConnectionItem(junction, j_anchor, dead, dead.anchors["P"])
    conn_dead.editor = editor
    scene.addItem(conn_dead)
    junction.connections.append(conn_dead)
    dead.connections.append(conn_dead)
    assert j_anchor.connection_count() == 3

    conn_dead.prepare_delete()
    scene.removeItem(conn_dead)
    app.processEvents()

    assert junction.scene() is None
    remaining = [c for c in scene.items() if isinstance(c, ConnectionItem)]
    assert len(remaining) == 1
    merged = remaining[0]
    assert {merged.source, merged.target} == {a, b}

    points = merged.get_path_points()
    _assert_orthogonal(points, "resultado do merge")

    # A forma continua saindo de a=(0,0) e chegando em b=(200,200) --
    # confirma que o merge não jogou fora a rota, só a reconectou.
    assert (points[0].x(), points[0].y()) == (0, 0)
    assert (points[-1].x(), points[-1].y()) == (200, 200)


def test_merge_orientation_is_correct_regardless_of_which_leg_is_first():
    """Bug real encontrado: reusar a mesma orientação "outro_lado até a
    junção" pras duas pernas do merge invertia a ordem de uma delas,
    ligando o ponto de passagem ao ponto errado da segunda perna e
    produzindo diagonal. Testa as duas ordens possíveis de
    node.connections[0]/[1] (a ordem de inserção determina qual perna
    vira "leg1" vs "leg2" dentro de _merge_junction_if_collapsed) --
    reconstruindo a cena do zero pra cada ordem, com pernas roteadas de
    verdade (via split_connection_at) em vez de waypoints inventados à
    mão, que podem não ser válidos pras margens reais da conexão."""
    for reverse_insertion_order in (False, True):
        scene = QGraphicsScene()
        editor = EditorState()
        editor.mode = EditorMode.CONNECT
        view = GraphicsView(editor)
        view.setScene(scene)

        a = _make_leaf(scene, 0, 0, ["right"])
        b = _make_leaf(scene, 200, 0, ["left"])
        conn = ConnectionItem(a, a.anchors["P"], b, b.anchors["P"])
        conn.editor = editor
        scene.addItem(conn)
        a.connections.append(conn)
        b.connections.append(conn)
        conn.get_path_points()

        j_anchor = view.split_connection_at(conn, QPointF(100, 0))
        app.processEvents()
        junction = j_anchor.node

        dead = _make_leaf(scene, 100, 100, ["top"])
        conn_dead = ConnectionItem(junction, j_anchor, dead, dead.anchors["P"])
        conn_dead.editor = editor
        scene.addItem(conn_dead)
        junction.connections.append(conn_dead)
        dead.connections.append(conn_dead)
        assert j_anchor.connection_count() == 3

        if reverse_insertion_order:
            junction.connections[0], junction.connections[1] = (
                junction.connections[1], junction.connections[0]
            )

        conn_dead.prepare_delete()
        scene.removeItem(conn_dead)
        app.processEvents()

        remaining = [c for c in scene.items() if isinstance(c, ConnectionItem)]
        assert len(remaining) == 1, f"reverse_insertion_order={reverse_insertion_order}"
        merged = remaining[0]
        _assert_orthogonal(
            merged.get_path_points(),
            f"merge com reverse_insertion_order={reverse_insertion_order}",
        )
        assert {merged.source, merged.target} == {a, b}
