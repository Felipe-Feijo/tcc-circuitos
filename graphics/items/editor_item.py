from PyQt6.QtWidgets import QGraphicsItem, QMenu
from PyQt6.QtCore import Qt

class EditorItem():
    def __init__(self):
        super().__init__()
        self.editor = None

    def set_editable(self, enabled: bool):
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, enabled)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, enabled)

    def mousePressEvent(self, event):
        if self.editor and self.editor.mode == "delete":
            self.scene().removeItem(self)
            self.editor.update_scene_rect()
            event.accept()
            return

        QGraphicsItem.mousePressEvent(self, event)

    def mouseReleaseEvent(self, event):
        QGraphicsItem.mouseReleaseEvent(self, event)
        if self.editor:
            self.editor.update_scene_rect()

    def contextMenuEvent(self, event):
        if not self.editor:
            return

        menu = QMenu()
        menu.addAction(self.editor.actions["mode_delete"])

        self.extend_context_menu(menu)

        menu.exec(event.screenPos())
        event.accept()

    def extend_context_menu(self, menu: QMenu):
        """Hook para subclasses"""
        pass