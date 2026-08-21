"""PressureLine: two terminal-sprite endpoints (left = PressureLine
itself, right = PressureLineTerminal) joined by a rail. Both endpoints'
simulation_cls is Junction -- a PressureLine domain node would be
identical pass-through behavior, so it's not reintroduced (see
docs/superpowers/specs/2026-08-21-expandable-items-junction-redesign-design.md)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.expandable.pressure_line import (
    PressureLine, PressureLineTerminal,
)
from graphics.items.base.nodes.paired_terminal_item import PairedTerminalItem
from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.node_item import NodeItem
from simulation.nodes.nodes import Junction


def test_pressure_line_has_single_anchor_x1():
    item = PressureLine(domain="pneumatic")
    assert list(item.anchors.keys()) == ["X1"]
    assert item.node_type == "pressure_line"
    assert item.simulation_cls is Junction
    meta = item.palette_meta()
    assert meta.domains == ("pneumatic",)


def test_pressure_line_terminal_is_not_palette_visible():
    assert PressureLineTerminal.palette_meta() is None


def test_pressure_line_terminal_is_plain_node_item_not_paired():
    assert not issubclass(PressureLineTerminal, PairedTerminalItem)
    assert issubclass(PressureLineTerminal, NodeItem)


def test_pressure_line_registered_in_class_registry():
    assert NodeItem.class_registry["PressureLine"] is PressureLine
    assert NodeItem.class_registry["PressureLineTerminal"] is PressureLineTerminal


def test_pressure_line_spawns_terminal_far_end_and_rail_not_a_third_pair():
    scene = QGraphicsScene()
    item = PressureLine(domain="pneumatic")
    scene.addItem(item)

    terminals = [i for i in scene.items() if isinstance(i, PressureLineTerminal)]
    conns = [i for i in scene.items() if isinstance(i, ConnectionItem)]
    assert len(terminals) == 1
    assert len(conns) == 1
    assert {conns[0].source, conns[0].target} == {item, terminals[0]}


def test_pressure_line_to_dict_from_dict_round_trip_no_respawn():
    scene = QGraphicsScene()
    item = PressureLine(domain="pneumatic")
    item.setPos(1.0, 2.0)
    scene.addItem(item)
    data = item.to_dict()

    scene2 = QGraphicsScene()
    restored = PressureLine.from_dict(data)
    scene2.addItem(restored)

    assert not any(isinstance(i, PressureLineTerminal) for i in scene2.items())
