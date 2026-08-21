"""Ground: a single-anchor 'X1' node whose far end (an existing
JunctionNodeItem) and rail are spawned by PairedTerminalItem the first
time it's added to a real scene."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.expandable.ground import Ground
from graphics.items.base.nodes.junction_node_item import JunctionNodeItem
from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.node_item import NodeItem
from simulation.nodes.ground import Ground as GroundNode


def test_ground_has_single_anchor_x1():
    item = Ground(domain="electric")
    assert list(item.anchors.keys()) == ["X1"]
    assert item.node_type == "ground"
    assert item.simulation_cls is GroundNode
    meta = item.palette_meta()
    assert meta.domains == ("electric",)


def test_ground_registered_in_class_registry():
    assert NodeItem.class_registry["Ground"] is Ground


def test_ground_spawns_junction_far_end_and_rail():
    scene = QGraphicsScene()
    item = Ground(domain="electric")
    scene.addItem(item)

    junctions = [i for i in scene.items() if isinstance(i, JunctionNodeItem)]
    conns = [i for i in scene.items() if isinstance(i, ConnectionItem)]
    assert len(junctions) == 1
    assert len(conns) == 1
    assert {conns[0].source, conns[0].target} == {item, junctions[0]}


def test_ground_to_dict_from_dict_round_trip_no_respawn():
    scene = QGraphicsScene()
    item = Ground(domain="electric")
    item.setPos(10.0, 20.0)
    scene.addItem(item)
    data = item.to_dict()

    scene2 = QGraphicsScene()
    restored = Ground.from_dict(data)
    scene2.addItem(restored)

    assert restored.pos().x() == 10.0
    assert restored.pos().y() == 20.0
    assert list(restored.anchors.keys()) == ["X1"]
    assert not any(isinstance(i, JunctionNodeItem) for i in scene2.items())


def test_ground_domain_marks_its_anchor_as_ground():
    node = GroundNode("g1", domain="electric")
    node.add_anchor("X1", "electric")
    node.update()
    assert node.get_anchor("X1").type == "ground"
    assert node.get_internal_connections() == []
