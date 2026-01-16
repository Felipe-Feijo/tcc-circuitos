
from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPen, QPainter, QPixmap
from math import hypot
from graphics.items.base.diagram_item_base import DiagramItemBase


class NodeItem(DiagramItemBase):
    def __init__(self):
        DiagramItemBase.__init__(self)
        self.anchors = []
        self.connections = []
        self._hover_anchor = None
        self.setAcceptHoverEvents(True)

        self.pixmap: QPixmap | None = None
        self.draw_selection = True

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

    def anchor_near_mouse(self, scene_pos):
        best_anchor = None
        best_dist = None

        for anchor in self.anchors:
            anchor_scene = self.mapToScene(anchor.pos)

            dx = scene_pos.x() - anchor_scene.x()
            dy = scene_pos.y() - anchor_scene.y()
            dist = hypot(dx, dy)

            if dist <= anchor.radius:
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best_anchor = anchor

        return best_anchor

    def hoverMoveEvent(self, event):
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
        return super().itemChange(change, value)
    
    def update_connections(self):
        for conn in self.connections:
            conn.update_path()

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
        if self.draw_selection and self.isSelected():
            pen = QPen(Qt.GlobalColor.blue, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(0, 0, self.width, self.height)