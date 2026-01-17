import os
import uuid
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF


from graphics.items.base.nodes.node_item import NodeItem
from ....anchors.anchor import AnchorItem


class GenericValve(NodeItem):
    def __init__(self, w=80, h=40, icon_path="resources/nodes/generic_valve/generic_valve.png"):
        super().__init__()

        self.id = str(uuid.uuid4())

        self.node_type = "generic_valve"
        self.width = w
        self.height = h

        if icon_path and os.path.isfile(icon_path):
            self.pixmap = QPixmap(icon_path)

        # Anchors do node
        self.anchors = [
            AnchorItem("left", QPointF(0, h/2), node=self),
            AnchorItem("right", QPointF(w, h/2), node=self),
            AnchorItem("top", QPointF(w/2, 0), node=self),
            AnchorItem("bottom", QPointF(w/2, h), node=self),
        ]




    

