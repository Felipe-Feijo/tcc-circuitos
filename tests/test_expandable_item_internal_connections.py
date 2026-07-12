import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.expandable.pressure_line import PressureLine
from graphics.items.base.connections.connection_item import ConnectionItem


def make_pressure_line(scene: QGraphicsScene, n_anchors: int) -> PressureLine:
    pl = PressureLine(domain="pneumatic")
    scene.addItem(pl)
    # DEFAULT_ANCHORS já cria X1, X2 — completa até n_anchors à direita.
    while len(pl.anchor_list) < n_anchors:
        pl.add_anchor_side("right")
    pl.update_internal_connections()
    return pl


def connect_external(scene: QGraphicsScene, node_a, anchor_name_a, node_b, anchor_name_b):
    """Simula uma conexão real feita pelo usuário entre dois anchors."""
    a1 = next(a for a in node_a.anchor_list if a.name == anchor_name_a)
    a2 = next(a for a in node_b.anchor_list if a.name == anchor_name_b)
    conn = ConnectionItem(node_a, a1, node_b, a2)
    scene.addItem(conn)
    node_a.connections.append(conn)
    node_b.connections.append(conn)
    return conn


def test_no_real_connections_creates_single_internal_connection():
    scene = QGraphicsScene()
    pl = make_pressure_line(scene, 6)

    assert len(pl.internal_connections) == 1
    conn = pl.internal_connections[0]
    assert {conn.source_anchor.name, conn.target_anchor.name} == {"X1", "X6"}


def test_real_connection_on_intermediate_anchor_splits_internal_connections():
    scene = QGraphicsScene()
    pl = make_pressure_line(scene, 6)
    other = make_pressure_line(scene, 2)

    connect_external(scene, pl, "X3", other, "X1")
    pl.update_internal_connections()

    assert len(pl.internal_connections) == 2
    pairs = {
        frozenset((c.source_anchor.name, c.target_anchor.name))
        for c in pl.internal_connections
    }
    assert pairs == {frozenset({"X1", "X3"}), frozenset({"X3", "X6"})}


def test_removing_external_connection_merges_internal_connections_back():
    scene = QGraphicsScene()
    pl = make_pressure_line(scene, 6)
    other = make_pressure_line(scene, 2)

    ext_conn = connect_external(scene, pl, "X3", other, "X1")
    pl.update_internal_connections()
    assert len(pl.internal_connections) == 2

    ext_conn.prepare_delete()
    scene.removeItem(ext_conn)
    if ext_conn in pl.connections:
        pl.connections.remove(ext_conn)

    pl.update_internal_connections()

    assert len(pl.internal_connections) == 1
    conn = pl.internal_connections[0]
    assert {conn.source_anchor.name, conn.target_anchor.name} == {"X1", "X6"}


def test_stale_internal_connection_item_is_removed_from_scene():
    scene = QGraphicsScene()
    pl = make_pressure_line(scene, 6)
    other = make_pressure_line(scene, 2)

    connect_external(scene, pl, "X3", other, "X1")
    pl.update_internal_connections()
    stale_candidates = [
        c for c in pl.internal_connections
        if {c.source_anchor.name, c.target_anchor.name} == {"X1", "X6"}
    ]
    assert stale_candidates == []  # o X1->X6 original não deve sobreviver
    for conn in pl.internal_connections:
        assert conn.scene() is scene
