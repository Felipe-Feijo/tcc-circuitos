# graphics/view.py
from PyQt6.QtWidgets import QGraphicsView
from PyQt6.QtCore import Qt

class GraphicsView(QGraphicsView):

    ZOOM_IN_FACTOR = 1.25
    ZOOM_OUT_FACTOR = 0.8

    def __init__(self, editor, *args):
        super().__init__(*args)
        self.editor = editor

        self._panning = False
        self._pan_start = None

        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)

    def zoom_in(self):
        self.scale(self.ZOOM_IN_FACTOR, self.ZOOM_IN_FACTOR)
        if self.editor:
            self.editor.update_scene_rect()

    def zoom_out(self):
        self.scale(self.ZOOM_OUT_FACTOR, self.ZOOM_OUT_FACTOR)
        if self.editor:
            self.editor.update_scene_rect()

    def zoom_to_contents(self):
        scene = self.scene()
        if not scene:
            return

        items_rect = scene.itemsBoundingRect()
        if items_rect.isNull():
            return

        self.fitInView(items_rect, Qt.AspectRatioMode.KeepAspectRatio)

        if self.editor:
            self.editor.update_scene_rect()

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.editor.mode == "add":
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
