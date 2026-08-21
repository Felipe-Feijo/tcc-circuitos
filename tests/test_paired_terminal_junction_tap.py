"""Integration: the rail ConnectionItem that PairedTerminalItem spawns
between Ground and its JunctionNodeItem far end accepts a junction tap
the same way any ordinary connection does -- the premise of this whole
redesign. See docs/superpowers/specs/2026-08-21-expandable-items-
junction-redesign-design.md."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene
from PyQt6.QtCore import QPointF

app = QApplication.instance() or QApplication([])

from editor.editor_state import EditorState
from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.expandable.ground import Ground
from graphics.view import GraphicsView


def test_tap_on_ground_rail_splits_it_into_two_children():
    scene = QGraphicsScene()
    editor = EditorState()
    view = GraphicsView(editor)
    view.setScene(scene)

    ground = Ground(domain="electric")
    ground.editor = editor
    scene.addItem(ground)

    rail = next(i for i in scene.items() if isinstance(i, ConnectionItem))
    points = rail.get_path_points()
    # _seg_hit_at only searches segments between points[1:-1] -- the raw
    # anchor endpoints (points[0] and points[-1]) are excluded, so the
    # split point must be picked from that same inner range.
    inner = points[1:-1]
    mid = max(1, (len(inner) - 1) // 2)
    mid_point = QPointF(
        (inner[mid - 1].x() + inner[mid].x()) / 2,
        (inner[mid - 1].y() + inner[mid].y()) / 2,
    )

    j_anchor = view.split_connection_at(rail, mid_point)
    # The original connection's removal is deferred via
    # QTimer.singleShot(0, ...) (see split_connection_at's comment) --
    # same pattern as tests/test_view_connection_junction.py.
    app.processEvents()

    assert j_anchor is not None
    assert j_anchor.node is not ground
    remaining = [i for i in scene.items() if isinstance(i, ConnectionItem)]
    assert rail not in remaining
    assert len(remaining) == 2
