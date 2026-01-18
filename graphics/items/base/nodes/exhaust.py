import os
import uuid
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF


from graphics.items.base.nodes.node_item import NodeItem
from ....anchors.anchor import AnchorItem


class Exhaust(NodeItem):
    def __init__(self, icon_path="resources/nodes/exhaust/exhaust.png"):
        super().__init__()

        self.id = str(uuid.uuid4())

        self.node_type = "exhaust"

        if icon_path and os.path.isfile(icon_path):
            self.pixmap = QPixmap(icon_path)
    
        self.width = self.pixmap.width()
        self.height = self.pixmap.height()

        # Anchors do node
        self.anchors = [
            AnchorItem("R", QPointF(self.width*0.5, 0), node=self),
        ]


