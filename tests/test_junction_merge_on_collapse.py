"""Quando uma JunctionNodeItem cai de 3 pra 2 conexões vivas (um ramo foi
deletado), ela deixa de funcionar como um T de verdade -- as duas pernas
remanescentes devem se fundir de volta numa única ConnectionItem entre os
dois nós originais, e o nó da junção (agora redundante) deve sumir. Mesmo
gancho de prepare_delete() que já cuida do caso de 0 conexões (nó órfão),
mesmo padrão adiado (QTimer.singleShot) -- ver
tests/test_junction_orphan_cleanup.py."""
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


def _make_junction(scene, x, y, domain="electric"):
    junction = JunctionNodeItem(domain=domain)
    junction.setPos(x, y)
    scene.addItem(junction)
    return junction


def _attach(scene, node_a, anchor_a, node_b, anchor_b, waypoints=None):
    conn = ConnectionItem(node_a, anchor_a, node_b, anchor_b)
    if waypoints is not None:
        conn.waypoints = [QPointF(x, y) for x, y in waypoints]
        conn._waypoints_initialized = True
    scene.addItem(conn)
    node_a.connections.append(conn)
    node_b.connections.append(conn)
    return conn


def test_merge_collapses_straight_route_removing_redundant_waypoint():
    """Fonte -- (100,0) junção -- terra, tudo alinhado em y=0: depois do
    merge, o ponto da junção é colinear com o resto e deve ser descartado
    por _collapse_segment_corners -- a conexão fundida vira uma reta
    limpa, sem sobra de waypoint no meio."""
    scene = QGraphicsScene()

    source = _make_leaf(scene, 0, 0)
    ground = _make_leaf(scene, 200, 0)
    dead   = _make_leaf(scene, 100, 100)
    junction = _make_junction(scene, 100, 0)
    j_anchor = junction.anchors["J"]

    conn_source = _attach(scene, source, source.anchors["P"], junction, j_anchor)
    conn_ground = _attach(scene, junction, j_anchor, ground, ground.anchors["P"])
    conn_dead   = _attach(scene, junction, j_anchor, dead, dead.anchors["P"])
    conn_source.get_path_points()
    conn_ground.get_path_points()

    assert j_anchor.connection_count() == 3

    conn_dead.prepare_delete()
    scene.removeItem(conn_dead)

    # Adiado -- nada mudou ainda no mesmo tick.
    assert junction.scene() is scene
    assert len(scene.items()) > 0

    app.processEvents()

    # Junção e as duas pernas antigas sumiram; sobrou 1 conexão direta.
    assert junction.scene() is None
    assert conn_source.scene() is None
    assert conn_ground.scene() is None

    remaining = [i for i in scene.items() if isinstance(i, ConnectionItem)]
    assert len(remaining) == 1
    merged = remaining[0]
    assert {merged.source, merged.target} == {source, ground}
    assert source.connections == [merged]
    assert ground.connections == [merged]

    # Rota reta em y=0 -- o ponto da junção (100,0) era colinear com tudo,
    # _collapse_segment_corners deve tê-lo descartado.
    for wp in merged.waypoints:
        assert abs(wp.y() - 0) < 0.5


def test_merge_preserves_a_genuine_bend_at_the_junction_point():
    """Fonte em (0,0) saindo pra direita, junção em (100,50) (fora da
    reta), terra em (200,50) -- o ponto da junção NÃO é colinear com o
    segmento de saída da fonte, então precisa sobreviver ao merge como
    waypoint de verdade (senão a rota corta caminho na diagonal)."""
    scene = QGraphicsScene()

    source = _make_leaf(scene, 0, 0)
    ground = _make_leaf(scene, 200, 50)
    junction = _make_junction(scene, 100, 50)
    j_anchor = junction.anchors["J"]

    # Rota deliberada: fonte -> (100,0) -> (100,50)=junção -- um cotovelo
    # de verdade antes da junção, não uma reta.
    conn_source = _attach(scene, source, source.anchors["P"], junction, j_anchor,
                           waypoints=[(100, 0)])
    conn_ground = _attach(scene, junction, j_anchor, ground, ground.anchors["P"])
    dead = _make_leaf(scene, 100, 150)
    conn_dead = _attach(scene, junction, j_anchor, dead, dead.anchors["P"])

    assert j_anchor.connection_count() == 3

    conn_dead.prepare_delete()
    scene.removeItem(conn_dead)
    app.processEvents()

    remaining = [i for i in scene.items() if isinstance(i, ConnectionItem)]
    assert len(remaining) == 1
    merged = remaining[0]
    assert {merged.source, merged.target} == {source, ground}

    # O cotovelo em (100,0) E o ponto da antiga junção (100,50) precisam
    # dos dois sobreviverem -- nem um nem outro é redundante aqui.
    xs_ys = [(round(wp.x()), round(wp.y())) for wp in merged.waypoints]
    assert (100, 0) in xs_ys
    assert (100, 50) in xs_ys


def test_merge_works_regardless_of_which_side_the_junction_is_on():
    """As duas pernas remanescentes podem ter a junção como source OU
    como target, em qualquer combinação -- o merge precisa acertar a
    orientação dos waypoints nos dois casos, não só no padrão "canônico"
    que split_connection_at sempre produz (source->junção,
    junção->target)."""
    scene = QGraphicsScene()

    a = _make_leaf(scene, 0, 0)
    b = _make_leaf(scene, 200, 0)
    dead = _make_leaf(scene, 100, 100)
    junction = _make_junction(scene, 100, 0)
    j_anchor = junction.anchors["J"]

    # As duas pernas com a junção como TARGET (o oposto do padrão usual).
    conn_a = _attach(scene, a, a.anchors["P"], junction, j_anchor)
    conn_b = _attach(scene, b, b.anchors["P"], junction, j_anchor)
    conn_dead = _attach(scene, junction, j_anchor, dead, dead.anchors["P"])

    assert j_anchor.connection_count() == 3

    conn_dead.prepare_delete()
    scene.removeItem(conn_dead)
    app.processEvents()

    remaining = [i for i in scene.items() if isinstance(i, ConnectionItem)]
    assert len(remaining) == 1
    merged = remaining[0]
    assert {merged.source, merged.target} == {a, b}
    assert a.connections == [merged]
    assert b.connections == [merged]


def test_junction_with_only_two_connections_from_the_start_is_untouched():
    """Merge só dispara via prepare_delete() (uma deleção de verdade) --
    uma junção que nasceu com só 2 conexões (nunca teve 3, nunca teve nada
    deletado) não deve ser mexida."""
    scene = QGraphicsScene()

    source = _make_leaf(scene, 0, 0)
    ground = _make_leaf(scene, 200, 0)
    junction = _make_junction(scene, 100, 0)
    j_anchor = junction.anchors["J"]

    conn_source = _attach(scene, source, source.anchors["P"], junction, j_anchor)
    conn_ground = _attach(scene, junction, j_anchor, ground, ground.anchors["P"])

    app.processEvents()

    assert junction.scene() is scene
    assert conn_source.scene() is scene
    assert conn_ground.scene() is scene
    assert j_anchor.connection_count() == 2
