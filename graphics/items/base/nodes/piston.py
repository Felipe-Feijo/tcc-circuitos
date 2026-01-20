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

        self.icon_retracted = QPixmap("resources/nodes/piston/piston.png")
        self.icon_extended = QPixmap("resources/nodes/piston/piston_extended.png")

        self.pixmap = self.icon_retracted

        self.width = self.pixmap.width()
        self.height = self.pixmap.height()

        self.anchors = [
            AnchorItem("A", QPointF(self.width * 0.0621, self.height), node=self),
        ]

    def set_extended(self, extended: bool):
        self.pixmap = self.icon_extended if extended else self.icon_retracted
        self.update()