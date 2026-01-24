
from PyQt6.QtGui import QPainter, QColor, QBrush, QPixmap, QTransform, QPainterPath
from PyQt6.QtCore import QPointF, QRectF



from graphics.items.base.nodes.node_item import NodeItem
from ....anchors.anchor import AnchorItem
ACTUATOR_DICT = {
    "button": {
        "sprite_active_path": "resources/actuators/button_active.png",
        "sprite_inactive_path": "resources/actuators/button_inactive.png",
        "mirrored": True
    },
}

class Valve_4_2_Ways(NodeItem):

    def __init__(self, actuator_size=30):
        super().__init__()

        self.node_type = "valve_4_2_ways"


        self.actuators = {
            "left": "button",   # apenas o tipo
            "right": "button",  # apenas o tipo
        }

        for actuator_type, data in ACTUATOR_DICT.items():
            if "sprite_active" not in data:
                data["sprite_active"] = QPixmap(data["sprite_active_path"])
                data["sprite_inactive"] = QPixmap(data["sprite_inactive_path"])

        self.body_left_icon = QPixmap("resources/nodes/valve_4_2_ways/valve_4_2_body_left.png")
        self.body_right_icon = QPixmap("resources/nodes/valve_4_2_ways/valve_4_2_body_right.png")
        self.body_sprite = self.body_right_icon

        # Dimensões do body
        self.width = self.body_sprite.width()
        self.height = self.body_sprite.height()

        # Anchors nos cantos do body
        self.add_anchor(AnchorItem("P", QPointF(self.width*191/300, self.height), node=self))               # superior esquerdo
        self.add_anchor(AnchorItem("A", QPointF(self.width*191/300, 0), node=self))      # superior direito
        self.add_anchor(AnchorItem("B", QPointF(self.width*256/300, 0), node=self))  # inferior direito
        self.add_anchor(AnchorItem("R", QPointF(self.width*256/300, self.height), node=self))     # inferior esquerdo

        # Bits dos atuadores
        self.bits = {"left": 0, "right": 0}


        self.max_offset_x = 147  # deslocamento máximo do body ao ativar o atuador esquerdo

        # Cria os rects dos atuadores com base no sprite e posição relativa ao body
        self.actuator_rects = {}

        for side in ["left", "right"]:
            actuator_type = ACTUATOR_DICT.get(self.actuators.get(side))
            if not actuator_type:
                continue
            sprite = actuator_type["sprite_active"]  # ou inactive, só para pegar tamanho
            w, h = sprite.width(), sprite.height()

            if side == "left":
                x = -w  # encostado na borda esquerda do body
            else:
                x = self.width  # encostado na borda direita do body

            y = self.height/2 - h/2  # centralizado vertical

            self.actuator_rects[side] = QRectF(x, y, w, h)

    # --------------------------
    # Retângulo delimitador
    # --------------------------
    def boundingRect(self) -> QRectF:
        """Retângulo total incluindo body, atuadores e deslocamento máximo."""
        margin = 10
        body_w, body_h = self.width, self.height

        # se os rects ainda não existirem, usamos tamanho padrão do body ou 0
        left_w = left_h = right_w = right_h = 0
        if hasattr(self, "actuator_rects"):
            left_rect = self.actuator_rects.get("left")
            if left_rect:
                left_w, left_h = left_rect.width(), left_rect.height()
            right_rect = self.actuator_rects.get("right")
            if right_rect:
                right_w, right_h = right_rect.width(), right_rect.height()

        leftmost_x = -left_w - margin
        total_width = body_w + left_w + right_w + getattr(self, "max_offset_x", 0) + 2*margin

        top_margin = max(0, (left_h - body_h)/2)
        bottom_margin = max(0, (right_h - body_h)/2)
        top_y = -top_margin - margin
        total_height = body_h + top_margin + bottom_margin + 2*margin

        return QRectF(leftmost_x, top_y, total_width, total_height)


    # --------------------------
    # Desenho
    # --------------------------
    def paint(self, painter, option, widget=None):
        # Corpo
        if self.bits["left"] == 1 and self.bits["right"] == 0:
            self.body_sprite = self.body_left_icon
            self.visual_offset = QPointF(self.max_offset_x, 0) 
        elif self.bits["left"] == 0 and self.bits["right"] == 1:
            self.body_sprite = self.body_right_icon
            self.visual_offset = QPointF(0, 0)  # sem deslocamento

        painter.drawPixmap(
                int(self.visual_offset.x()),
                int(self.visual_offset.y()),
                self.body_sprite
            )
        
        # calcula body_rect (posição + tamanho)
        body_rect = QRectF(
            self.visual_offset.x(),
            self.visual_offset.y(),
            self.width,
            self.height
        )

        for side in ["left", "right"]:
            actuator_type = ACTUATOR_DICT.get(self.actuators.get(side))
            if not actuator_type or not actuator_type.get("sprite_active") or not actuator_type.get("sprite_inactive"):
                continue  # pular se não houver atuador

            sprite = actuator_type["sprite_active"] if self.bits[side] else actuator_type["sprite_inactive"]

            # espelha o sprite se necessário
            if side == "right" and actuator_type.get("mirrored", False):
                sprite = sprite.transformed(QTransform().scale(-1, 1))

            # posição relativa ao body
            if side == "left":
                x = body_rect.x() - sprite.width()
            else:
                x = body_rect.x() + body_rect.width()

            y = body_rect.y() + (body_rect.height() - sprite.height()) / 2
            painter.drawPixmap(int(x), int(y), sprite)

        self.paint_selection_feedback(painter)

    # --------------------------
    # Clique do mouse
    # --------------------------
    def mousePressEvent(self, event):
        pos = event.pos()

        if not hasattr(self, "actuator_rects"):
            super().mousePressEvent(event)
            return
        if self.simulation_mode:
            for side, rect in self.actuator_rects.items():
                if rect.translated(self.visual_offset).contains(pos):
                    # inverte o bit do atuador
                    self.bits[side] ^= 1
                    self.command.emit(self.id, {
                        "type": "button",
                        "action": "press" if self.bits[side] else "release",
                        "side": side
                    })
                    # apenas atualiza o visual (paint vai usar o bit para desenhar)
                    self.update()
                    event.accept()
                    return

        super().mousePressEvent(event)


    def shape(self):
        path = QPainterPath()

        # body
        body_rect = QRectF(
            self.visual_offset.x(),
            self.visual_offset.y(),
            self.width,
            self.height
        )
        path.addRect(body_rect)

        # atuadores, se existirem
        if hasattr(self, "actuator_rects"):
            left_rect = self.actuator_rects.get("left")
            right_rect = self.actuator_rects.get("right")
            if left_rect:
                path.addRect(left_rect.translated(self.visual_offset))
            if right_rect:
                path.addRect(right_rect.translated(self.visual_offset))

        return path