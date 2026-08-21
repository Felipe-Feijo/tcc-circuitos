"""AnchorItem.always_visible: an escape hatch from the generic "dot only
at 3+ connections" rule, for a specific anchor that needs to read as a
terminal even with a single connection. Used by Ground/VoltageSource's
far end (a JunctionNodeItem with no sprite of its own -- without a
forced dot, the rail would visually end at nothing). Ordinary junctions
(anchor with always_visible left False, the default) are unaffected."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene
from PyQt6.QtGui import QColor

app = QApplication.instance() or QApplication([])

from graphics.anchors.anchor import AnchorItem
from graphics.items.base.nodes.junction_node_item import JunctionNodeItem
from graphics.items.base.nodes.expandable.ground import Ground
from graphics.items.base.nodes.expandable.pressure_line import PressureLine, PressureLineTerminal


def _is_dot_visible(anchor: AnchorItem) -> bool:
    return anchor.brush().color() != QColor(0, 0, 0, 0)


def test_always_visible_defaults_to_false():
    item = JunctionNodeItem(domain="electric")
    assert item.anchors["J"].always_visible is False


def test_always_visible_forces_dot_below_three_connections():
    item = JunctionNodeItem(domain="electric")
    anchor = item.anchors["J"]

    anchor.always_visible = True
    anchor.refresh_junction_dot()

    assert _is_dot_visible(anchor)


def test_ordinary_junction_still_needs_three_connections():
    item = JunctionNodeItem(domain="electric")
    anchor = item.anchors["J"]

    anchor.refresh_junction_dot()  # 0 connections, always_visible still False

    assert not _is_dot_visible(anchor)


def test_ground_far_end_dot_is_visible_with_a_single_connection():
    scene = QGraphicsScene()
    item = Ground(domain="electric")
    scene.addItem(item)

    junction = next(i for i in scene.items() if isinstance(i, JunctionNodeItem))
    anchor = junction.anchors["J"]

    assert anchor.connection_count() == 1
    assert anchor.always_visible is True
    assert _is_dot_visible(anchor)


def test_pressure_line_far_end_does_not_force_a_dot():
    scene = QGraphicsScene()
    item = PressureLine(domain="pneumatic")
    scene.addItem(item)

    terminal = next(i for i in scene.items() if isinstance(i, PressureLineTerminal))
    anchor = terminal.anchors["X1"]

    assert anchor.always_visible is False
    assert not _is_dot_visible(anchor)
