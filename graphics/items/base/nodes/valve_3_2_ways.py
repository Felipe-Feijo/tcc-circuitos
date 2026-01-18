import os
import uuid
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QRectF


from graphics.items.base.nodes.node_item import NodeItem
from ....anchors.anchor import AnchorItem


class Valve_3_2_Ways(NodeItem):
    def __init__(self, icon_path="resources/nodes/valve_3_2_ways/valve_3_2_ways.png"):
        super().__init__()

        self.id = str(uuid.uuid4())

        self.node_type = "valve_3_2_ways"

        if icon_path and os.path.isfile(icon_path):
            self.pixmap = QPixmap(icon_path)
    
        self.width = self.pixmap.width()
        self.height = self.pixmap.height()

        # Anchors do node
        self.anchors = [
            AnchorItem("A", QPointF(self.width*0.66, 0), node=self),
            AnchorItem("R", QPointF(self.width*0.5411, self.height), node=self),
            AnchorItem("P", QPointF(self.width*0.66, self.height), node=self),
        ]

        self.button_rect = QRectF(
            0,                    # x
            self.height * 0.48,   # y
            self.width * 0.20,    # w
            self.height * 0.47     # h
        )

    def mousePressEvent(self, event):
        if self.button_rect.contains(event.pos()):
            self.on_button_pressed()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.button_rect.contains(event.pos()):
            self.on_button_released()
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def on_button_pressed(self):
        self.buttonCommand.emit(self.id, "press")

    def on_button_released(self):
        self.buttonCommand.emit(self.id, "release")



    

