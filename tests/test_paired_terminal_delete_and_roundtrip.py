"""Delete behavior and save/load round trip for the paired-terminal model
(Ground/VoltageSource/PressureLine) -- see the "Delete behavior" and
"Testing" sections of
docs/superpowers/specs/2026-08-21-expandable-items-junction-redesign-design.md.

No special "pair" identity exists after creation, so all three delete
cases (rail alone, node_a, node_b) fall through to generic delete
mechanics. These tests exercise real Qt objects and the actual deferred-
removal pattern (QTimer.singleShot(0, ...) + QApplication.processEvents())
already used by tests/test_junction_orphan_cleanup.py and
tests/test_junction_merge_on_collapse.py.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene

app = QApplication.instance() or QApplication([])

from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.expandable.ground import Ground
from graphics.items.base.nodes.expandable.pressure_line import (
    PressureLine,
    PressureLineTerminal,
)
from graphics.items.base.nodes.junction_node_item import JunctionNodeItem
from graphics.items.base.nodes.node_item import NodeItem
from graphics.scene import GraphicsScene
from persistence.serializer import deserialize_scene, serialize_scene


def _rail_of(scene):
    return next(i for i in scene.items() if isinstance(i, ConnectionItem))


def test_delete_rail_alone_survives_ground_and_orphans_junction():
    scene = QGraphicsScene()
    ground = Ground(domain="electric")
    scene.addItem(ground)

    junction = next(i for i in scene.items() if isinstance(i, JunctionNodeItem))
    rail = _rail_of(scene)
    j_anchor = junction.anchors["J"]

    assert j_anchor.connection_count() == 1

    rail.prepare_delete()
    scene.removeItem(rail)

    # Before the deferred cleanup runs, the junction is still present
    # (0 connections, not yet swept).
    assert junction.scene() is scene

    app.processEvents()

    # Ground survives untouched; the now-orphaned JunctionNodeItem (0
    # connections) is swept by the existing orphan-cleanup mechanism.
    assert ground.scene() is scene
    assert junction.scene() is None
    assert list(ground.anchors.keys()) == ["X1"]


def _delete_node_and_its_connections(scene, node):
    """Mirrors editor/delete_manager.py's DeleteManager.do_delete() for a
    single selected node: prepare_delete() every attached connection and
    the node itself, then remove them from the scene."""
    connections = list(node.connections)
    for conn in connections:
        conn.prepare_delete()
    node.prepare_delete()
    for conn in connections:
        if conn.scene():
            scene.removeItem(conn)
    if node.scene():
        scene.removeItem(node)


def test_delete_node_a_removes_rail_and_survives_node_b():
    # Uses PressureLine, not Ground: node_b here is a PressureLineTerminal
    # with a visible sprite, which stays behind inert at 0 connections
    # (per spec) -- unlike Ground's bare JunctionNodeItem far end, which
    # would be orphan-cleaned away, making "survives" untestable.
    scene = QGraphicsScene()
    pressure_line = PressureLine(domain="pneumatic")
    scene.addItem(pressure_line)

    terminal = next(i for i in scene.items() if isinstance(i, PressureLineTerminal))
    rail = _rail_of(scene)

    _delete_node_and_its_connections(scene, pressure_line)
    app.processEvents()

    assert pressure_line.scene() is None
    assert rail.scene() is None
    # node_b (the far end) survives, inert with 0 connections.
    assert terminal.scene() is scene
    assert terminal.anchors["X1"].connection_count() == 0


def test_delete_node_b_removes_rail_and_survives_node_a():
    scene = QGraphicsScene()
    pressure_line = PressureLine(domain="pneumatic")
    scene.addItem(pressure_line)

    terminal = next(i for i in scene.items() if isinstance(i, PressureLineTerminal))
    rail = _rail_of(scene)

    _delete_node_and_its_connections(scene, terminal)
    app.processEvents()

    assert terminal.scene() is None
    assert rail.scene() is None
    assert pressure_line.scene() is scene
    assert list(pressure_line.anchors.keys()) == ["X1"]


def test_full_pair_save_load_round_trip_no_duplicate_far_ends():
    scene = GraphicsScene()

    ground = Ground(domain="electric")
    scene.addItem(ground)

    pressure_line = PressureLine(domain="pneumatic")
    scene.addItem(pressure_line)

    nodes = [i for i in scene.items() if isinstance(i, NodeItem)]
    conns = [i for i in scene.items() if isinstance(i, ConnectionItem)]
    assert len(nodes) == 4
    assert len(conns) == 2

    data = serialize_scene(scene)
    assert len(data["nodes"]) == 4
    assert len(data["connections"]) == 2

    new_scene = GraphicsScene()
    created = deserialize_scene(data, new_scene, editor=None)

    restored_nodes = [i for i in created if isinstance(i, NodeItem)]
    restored_conns = [i for i in created if isinstance(i, ConnectionItem)]

    assert len(restored_nodes) == 4
    assert len(restored_conns) == 2
    assert len([n for n in restored_nodes if isinstance(n, Ground)]) == 1
    assert len([n for n in restored_nodes if isinstance(n, JunctionNodeItem)]) == 1
    assert len([n for n in restored_nodes if isinstance(n, PressureLine)]) == 1
    assert len(
        [n for n in restored_nodes if isinstance(n, PressureLineTerminal)]
    ) == 1

    new_scene._test_ref = new_scene  # keeps it alive, see test_junction_save_load.py
