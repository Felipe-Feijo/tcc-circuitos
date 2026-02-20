from PyQt6.QtWidgets import QGraphicsItem, QMenu, QGraphicsObject
from PyQt6.QtGui import QPen
from PyQt6.QtCore import Qt


class DiagramItemBase(QGraphicsObject):
    def __init__(self):
        super().__init__()
        self.editor = None
        self.draw_selection = True

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

    def paint_selection_feedback(self, painter):
        """Desenhar destaque de seleção baseado no shape real."""
        if self.draw_selection and self.isSelected():
            pen = QPen(Qt.GlobalColor.blue, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            # desenha o shape real, incluindo body + botões na posição atual
            painter.drawPath(self.shape())

    def update_from_domain(self, domain_node):
        pass