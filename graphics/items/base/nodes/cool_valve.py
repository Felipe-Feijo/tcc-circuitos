import os
import uuid
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF


from graphics.items.base.nodes.node_item import NodeItem
from ....anchors.anchor import AnchorItem


class CoolValve(NodeItem):
    def __init__(self, w=40, h=80, icon_path="resources/nodes/cool_valve/cool_valve.png"):
        super().__init__()

        self.id = str(uuid.uuid4())

        self.node_type = "cool_valve"
        self.width = w
        self.height = h

        if icon_path and os.path.isfile(icon_path):
            self.pixmap = QPixmap(icon_path)

        # Anchors do node
        self.anchors = [
            AnchorItem("bottom_left", QPointF(w, 0), node=self),
            AnchorItem("top_left", QPointF(0, 0), node=self),
            AnchorItem("bottom_right", QPointF(w, h), node=self),
            AnchorItem("top_right", QPointF(0, h), node=self),
        ]
