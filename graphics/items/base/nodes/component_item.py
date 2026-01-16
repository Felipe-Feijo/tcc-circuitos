import os
import uuid
from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF


from graphics.items.base.nodes.node_item import NodeItem
from ....anchors.anchor import AnchorItem


class ComponentItem(NodeItem):
    def __init__(self, w=80, h=40, icon_path=None):
        super().__init__()

        self.id = str(uuid.uuid4())

        self.component_type = "generic_component"
        self.width = w
        self.height = h

        if icon_path and os.path.isfile(icon_path):
            self.pixmap = QPixmap(icon_path)

        # Anchors do componente
        self.anchors = [
            AnchorItem("left", QPointF(0, h/2), component=self),
            AnchorItem("right", QPointF(w, h/2), component=self),
            AnchorItem("top", QPointF(w/2, 0), component=self),
            AnchorItem("bottom", QPointF(w/2, h), component=self),
        ]




    

