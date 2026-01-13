from PyQt6.QtWidgets import QGraphicsRectItem, QMenu
from PyQt6.QtGui import QBrush, QPen, QColor
from PyQt6.QtCore import Qt, QRectF

class ComponentItem(QGraphicsRectItem):
    def __init__(self, x=0, y=0, w=80, h=40):
        super().__init__(QRectF(0, 0, w, h))
        self.editor = None

        self.setBrush(QBrush(QColor("#ADD8E6")))
        self.setPen(QPen(Qt.GlobalColor.black, 2))

        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)

        self.setPos(x, y)

    def mousePressEvent(self, event):
        if self.editor and self.editor.mode == "delete":
            self.scene().removeItem(self)
            self.editor.update_scene_rect()
            event.accept()
            return

        super().mousePressEvent(event)
        # ❌ NÃO chamar update_scene_rect aqui

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)

        if self.editor:
            self.editor.update_scene_rect()

    def contextMenuEvent(self, event):
        if not self.editor:
            return

        menu = QMenu()
        menu.addAction(self.editor.actions["mode_delete"])
        menu.exec(event.screenPos())
        event.accept()
