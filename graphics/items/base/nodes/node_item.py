
from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPen, QPainter, QPixmap
from graphics.items.base.diagram_item_base import DiagramItemBase


class NodeItem(DiagramItemBase):
    buttonCommand = pyqtSignal(str, str) #node_id, command
    def __init__(self):
        DiagramItemBase.__init__(self)
        self.anchors = []
        self.connections = []
        self.setAcceptHoverEvents(True)


        self.pixmap: QPixmap | None = None
        self.draw_selection = True

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)


    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for conn in self.connections:
                conn.update()
        return super().itemChange(change, value)
    
    def update_connections(self):
        for conn in self.connections:
            conn.update()

    def prepare_delete(self):
        print(f"Deleting NodeItem at {self.pos()}")

        print(f"Node at {self.pos()} has connections:")
        for c in self.connections:
            print(" -", c, "to", c.target)
        # desconecta todas as conexões
        for conn in self.connections[:]:  # copia da lista
            conn.prepare_delete()           # <- chama prepare_delete da conexão
            if conn.scene():                # remove visualmente
                conn.scene().removeItem(conn)

        self.connections.clear()
        print(f"All connections detached from NodeItem at {self.pos()}\n")

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter: QPainter, option, widget=None):

        # ícone (se existir)
        if self.pixmap and not self.pixmap.isNull():
            scaled = self.pixmap.scaled(
                self.width,
                self.height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            pos = QPointF(
                (self.width - scaled.width()) / 2,
                (self.height - scaled.height()) / 2
            )
            painter.drawPixmap(pos, scaled)

        # feedback de seleção
        self.paint_selection_feedback(painter)