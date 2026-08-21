"""VoltageSource: mirrors Ground -- single anchor 'X1', far end is a
JunctionNodeItem spawned by PairedTerminalItem."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.expandable.voltage_source import VoltageSource
from graphics.items.base.nodes.junction_node_item import JunctionNodeItem
from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.node_item import NodeItem
from simulation.nodes.voltage_source import VoltageSource as VoltageSourceNode


def test_voltage_source_has_single_anchor_x1():
    item = VoltageSource(domain="electric")
    assert list(item.anchors.keys()) == ["X1"]
    assert item.node_type == "voltage_source"
    assert item.simulation_cls is VoltageSourceNode


def test_voltage_source_registered_in_class_registry():
    assert NodeItem.class_registry["VoltageSource"] is VoltageSource


def test_voltage_source_spawns_junction_far_end_and_rail():
    scene = QGraphicsScene()
    item = VoltageSource(domain="electric")
    scene.addItem(item)

    junctions = [i for i in scene.items() if isinstance(i, JunctionNodeItem)]
    conns = [i for i in scene.items() if isinstance(i, ConnectionItem)]
    assert len(junctions) == 1
    assert len(conns) == 1
    assert {conns[0].source, conns[0].target} == {item, junctions[0]}


def test_voltage_source_to_dict_from_dict_round_trip_no_respawn():
    scene = QGraphicsScene()
    item = VoltageSource(domain="electric")
    item.setPos(5.0, 6.0)
    scene.addItem(item)
    data = item.to_dict()

    scene2 = QGraphicsScene()
    restored = VoltageSource.from_dict(data)
    scene2.addItem(restored)

    assert restored.pos().x() == 5.0
    assert restored.pos().y() == 6.0
    assert not any(isinstance(i, JunctionNodeItem) for i in scene2.items())


def test_voltage_source_domain_marks_its_anchor_as_source():
    node = VoltageSourceNode("v1", domain="electric")
    node.add_anchor("X1", "electric")
    node.update()
    assert node.get_anchor("X1").type == "source"
    assert node.get_internal_connections() == []
