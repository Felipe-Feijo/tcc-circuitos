"""Wheel zoom keeps the scene point under the cursor fixed, in every mode.

Regression: in ADD mode GraphicsView.mouseMoveEvent returns early without
calling QGraphicsView.mouseMoveEvent, so Qt's internal last-mouse-move
scene point (used by AnchorUnderMouse) went stale and zoom anchored to
wherever the cursor was before entering ADD mode."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from PyQt6.QtWidgets import QApplication, QGraphicsScene
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QWheelEvent

app = QApplication.instance() or QApplication([])

from editor.editor_state import EditorState
from editor.mode import EditorMode
from graphics.view import GraphicsView


def _wheel(view, pos: QPoint, delta: int) -> None:
    ev = QWheelEvent(
        QPointF(pos), QPointF(view.viewport().mapToGlobal(pos)),
        QPoint(0, 0), QPoint(0, delta),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )
    view.wheelEvent(ev)


@pytest.mark.parametrize("mode", [EditorMode.SELECT, EditorMode.ADD, EditorMode.CONNECT])
@pytest.mark.parametrize("delta", [120, -120])
def test_wheel_zoom_keeps_point_under_cursor(mode, delta):
    editor = EditorState()
    scene = QGraphicsScene()
    scene.setSceneRect(QRectF(-5000, -5000, 10000, 10000))
    view = GraphicsView(editor, scene)
    editor.update_scene_rect = lambda: None
    view.resize(800, 600)
    view.show()
    app.processEvents()
    editor.mode = mode

    cursor = QPoint(150, 120)
    before = view.mapToScene(cursor)
    _wheel(view, cursor, delta)
    after = view.mapToScene(cursor)

    assert abs(after.x() - before.x()) < 2.0
    assert abs(after.y() - before.y()) < 2.0
    view.close()
