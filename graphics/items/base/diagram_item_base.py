from PyQt6.QtWidgets import QGraphicsItem, QMenu

class DiagramItemBase(QGraphicsItem):
    def __init__(self):
        super().__init__()
        self.editor = None

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        
    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
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
        pass
