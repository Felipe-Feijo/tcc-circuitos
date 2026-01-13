from PyQt6.QtWidgets import QGraphicsRectItem
from PyQt6.QtGui import QBrush, QPen, QColor
from PyQt6.QtCore import Qt, QRectF

from graphics.items.editor_item import EditorItem

class ComponentItem(QGraphicsRectItem, EditorItem):
    def __init__(self, x=0, y=0, w=80, h=40):
        QGraphicsRectItem.__init__(self, QRectF(0, 0, w, h))
        EditorItem.__init__(self)

        self.setBrush(QBrush(QColor("#ADD8E6")))
        self.setPen(QPen(Qt.GlobalColor.black, 2))

        self.setPos(x, y)
