# graphics/items/connection_item.py
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsItem
from PyQt6.QtGui import QPainterPath, QPen
from PyQt6.QtCore import Qt, QPointF
from graphics.items.base.diagram_item_base import DiagramItemBase


class ConnectionItem(QGraphicsPathItem, DiagramItemBase):
    def __init__(self, source_node, source_anchor, target_node=None, target_anchor=None):
        QGraphicsPathItem.__init__(self)
        DiagramItemBase.__init__(self)

        self.source = source_node
        self.source_anchor = source_anchor
        self.target = target_node
        self.target_anchor = target_anchor

        self.temp_target_pos = None

        self.setPen(QPen(Qt.GlobalColor.red, 2))
        self.setZValue(-10)


        self.update_path()

    def update_path(self):
        p1 = self.source_anchor.scenePos()

        if self.target:
            p2 = self.target_anchor.scenePos()
        else:
            if self.temp_target_pos is None:
                return
            p2 = self.temp_target_pos  # posição do mouse

        dx = abs(p2.x() - p1.x())
        dy = abs(p2.y() - p1.y())

        if dx > dy:
            mid = QPointF(p2.x(), p1.y())
        else:
            mid = QPointF(p1.x(), p2.y())

        path = QPainterPath(p1)
        path.lineTo(mid)
        path.lineTo(p2)

        self.setPath(path)

    def update_temp_endpoint(self, scene_pos):
        self.temp_target_pos = scene_pos
        self.update_path()

    def prepare_delete(self):
        """Remove referências nos nós antes de apagar da cena, com feedback."""
        src_pos = self.source.pos() if self.source else "None"
        tgt_pos = self.target.pos() if self.target else "None"
        
        print(f"Deleting Connection: {src_pos} -> {tgt_pos}")

        # Remove referência no source
        if self.source and self in self.source.connections:
            self.source.connections.remove(self)
            print(f" - Removed from source node at {src_pos}")

        # Remove referência no target
        if self.target and self in self.target.connections:
            self.target.connections.remove(self)
            print(f" - Removed from target node at {tgt_pos}")

        # Desconecta anchors
        self.source_anchor = None
        self.target_anchor = None
        print(f" - Anchors disconnected\n")