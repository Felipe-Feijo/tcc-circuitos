# graphics/items/connection_item.py
from PyQt6.QtWidgets import QGraphicsPathItem
from PyQt6.QtGui import QPainterPath, QPen
from PyQt6.QtCore import Qt, QPointF

class ConnectionItem(QGraphicsPathItem):
    def __init__(self, source, source_anchor, target=None, target_anchor=None):
        super().__init__()
        self.source = source
        self.source_anchor = source_anchor
        self.target = target
        self.target_anchor = target_anchor

        self.temp_target_pos = None

        self.source.connections.append(self)

        if self.target:
            self.target.connections.append(self)

        self.setPen(QPen(Qt.GlobalColor.red, 2))
        self.setZValue(-1)
        self.update_path()

    def update_path(self):
        p1 = self.source.mapToScene(self.source_anchor.pos)

        if self.target:
            p2 = self.target.mapToScene(self.target_anchor.pos)
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