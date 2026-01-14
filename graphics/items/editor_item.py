from PyQt6.QtWidgets import QGraphicsItem, QMenu, QGraphicsRectItem
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from math import hypot

class EditorItem():
    def __init__(self):
        super().__init__()
        self.editor = None
        self.connections = []

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    def set_editable(self, enabled: bool):
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, enabled)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, enabled)


    def mouseReleaseEvent(self, event):
        QGraphicsItem.mouseReleaseEvent(self, event)
        if self.editor:
            self.editor.update_scene_rect()

    def contextMenuEvent(self, event):
        if not self.editor:
            return
        
        if self.editor.mode is not None:
            event.ignore()
            return

        scene = self.scene()

        if not self.isSelected():
            scene.clearSelection()
            self.setSelected(True)

        menu = QMenu()
        self.editor.active_context_menu = menu

        menu.addAction(self.editor.actions["delete"])

        self.extend_context_menu(menu)
        menu.exec(event.screenPos())

        self.editor.active_context_menu = None
        event.accept()

    def extend_context_menu(self, menu: QMenu):
        """Hook para subclasses"""
        pass

    def anchor_near_mouse(self, scene_pos):
        best_anchor = None
        best_dist = None

        for anchor in self.anchors:
            anchor_scene = self.mapToScene(anchor.pos)

            dx = scene_pos.x() - anchor_scene.x()
            dy = scene_pos.y() - anchor_scene.y()
            dist = hypot(dx, dy)

            # ajuste se você compensar zoom depois
            if dist <= anchor.radius:
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best_anchor = anchor

        return best_anchor
    
    def hoverMoveEvent(self, event):
        # só faz sentido no modo connect
        view = self.scene().views()[0]
        if view.editor.mode != "connect":
            if self._hover_anchor:
                self._hover_anchor = None
                self.unsetCursor()
                self.update()
            return

        anchor = self.anchor_near_mouse(event.scenePos())

        if anchor != self._hover_anchor:
            self._hover_anchor = anchor

            if anchor:
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.unsetCursor()

            self.update()

    def hoverLeaveEvent(self, event):
        self._hover_anchor = None
        self.unsetCursor()
        self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for conn in self.connections:
                conn.update_path()

        return QGraphicsRectItem.itemChange(self, change, value)
    
    def update_connections(self):
        for conn in self.connections:
            conn.update_path()
    