# graphics/view.py
from PyQt6.QtWidgets import QGraphicsView
from PyQt6.QtCore import Qt

class GraphicsView(QGraphicsView):
    def __init__(self, editor, *args):
        super().__init__(*args)
        self.editor = editor

        self._panning = False
        self._pan_start = None

        self.setDragMode(QGraphicsView.DragMode.NoDrag)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)

    def wheelEvent(self, event):
        zoom = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(zoom, zoom)

        if self.editor:
            self.editor.update_scene_rect()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.editor.add_mode:
            scene_pos = self.mapToScene(event.pos())
            self.editor.add_component_at(scene_pos.x(), scene_pos.y())
            event.accept()
            return

        if event.button() == Qt.MouseButton.RightButton:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()

            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            if self.editor:
                self.editor.update_scene_rect()
            return

        super().mouseReleaseEvent(event)
