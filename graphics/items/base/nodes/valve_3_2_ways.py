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

        self.icon_idle = QPixmap("resources/nodes/valve_3_2_ways/valve_3_2_ways.png")
        self.icon_pressed = QPixmap("resources/nodes/valve_3_2_ways/valve_3_2_ways_pressed.png")

        self.pixmap = self.icon_idle

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
        

    def boundingRect(self) -> QRectF:
        margin = 25  # ajuste conforme o deslocamento máximo do visual_offset
        return QRectF(
            0,
            0,
            self.width + margin * 2,
            self.height
        )

    def mousePressEvent(self, event):
        if self.button_rect.contains(event.pos()):
            self.on_button_pressed()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.on_button_released()
        event.accept()

    def on_button_pressed(self):
        if self.simulation_mode:
            self.pixmap = self.icon_pressed
            self.visual_offset = QPointF(96, 0)  # empurra levemente pro lado
            self.buttonCommand.emit(self.id, "press")

    def on_button_released(self):
        if self.simulation_mode:
            self.pixmap = self.icon_idle
            self.visual_offset = QPointF(0, 0)
            self.buttonCommand.emit(self.id, "release")


    


    

