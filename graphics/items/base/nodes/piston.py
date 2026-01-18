import os
import uuid
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF


from graphics.items.base.nodes.node_item import NodeItem
from ....anchors.anchor import AnchorItem


class Piston(NodeItem):
    def __init__(self, icon_path="resources/nodes/piston/piston.png"):
        super().__init__()

        self.id = str(uuid.uuid4())

        self.node_type = "piston"
        

        if icon_path and os.path.isfile(icon_path):
            self.pixmap = QPixmap(icon_path)

        self.width = self.pixmap.width()
        self.height = self.pixmap.height()

        # Anchors do node
        self.anchors = [
            AnchorItem("A", QPointF(self.width*0.0932, self.height), node=self),
        ]
