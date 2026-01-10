# graphics/items.py
from PyQt6.QtWidgets import QGraphicsRectItem
from PyQt6.QtGui import QBrush, QPen, QColor
from PyQt6.QtCore import Qt, QRectF

class ComponentItem(QGraphicsRectItem):
    def __init__(self, x=0, y=0, w=80, h=40):
        super().__init__(QRectF(0, 0, w, h))
        self.editor = None

        self.setBrush(QBrush(QColor("#ADD8E6")))
        self.setPen(QPen(Qt.GlobalColor.black, 2))
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self.setPos(x, y)

    def mousePressEvent(self, event):
        if self.editor and self.editor.delete_mode:
            self.scene().removeItem(self)
            self.editor.update_scene_rect()
            return
        super().mousePressEvent(event)
        if self.editor:
            self.editor.update_scene_rect()