import uuid
from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtGui import QBrush, QPen, QColor, QPainter
from PyQt6.QtCore import Qt, QRectF, QPointF


from graphics.items.nodes.node_item import NodeItem
from ...anchors.anchor import AnchorItem


class ComponentItem(NodeItem):
    def __init__(self, x=0, y=0, w=80, h=40, color="#ADD8E6"):
        super().__init__()

        self.id = str(uuid.uuid4())

        self.component_type = "generic_component"
        self.width = w
        self.height = h
        self.color = color

        # Anchors do componente
        self.anchors = [
            AnchorItem("left", QPointF(0, h/2), component=self),
            AnchorItem("right", QPointF(w, h/2), component=self),
            AnchorItem("top", QPointF(w/2, 0), component=self),
            AnchorItem("bottom", QPointF(w/2, h), component=self),
        ]

        # Posição inicial
        self.setPos(x, y)

        print("ComponentItem created at", x, y)

    # Qt precisa disso para renderizar e capturar mouse
    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.width, self.height)

    # Aqui você faz o desenho customizado
    def paint(self, painter: QPainter, option, widget=None):
        # cor do componente
        painter.setBrush(QBrush(QColor(self.color)))
        painter.setPen(QPen(QColor("black"), 2))
        painter.drawRect(0, 0, self.width, self.height)

        # feedback de seleção
        if self.isSelected():
            pen = QPen(Qt.GlobalColor.blue, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(0, 0, self.width, self.height)

    

