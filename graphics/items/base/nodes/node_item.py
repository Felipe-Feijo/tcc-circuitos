
import uuid
from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, pyqtProperty
from PyQt6.QtGui import QPen, QPainter, QPixmap
from graphics.anchors.anchor import AnchorItem
from graphics.items.base.diagram_item_base import DiagramItemBase


class NodeItem(DiagramItemBase):
    registry = {}
    command = pyqtSignal(str, dict) #node_id, command

    def __init_subclass__(cls):
            super().__init_subclass__()
            NodeItem.registry[cls.__name__] = cls

    def __init__(self):
        DiagramItemBase.__init__(self)

        self.id = str(uuid.uuid4())
        
        self.anchors = {}
        self.connections = []
        self.setAcceptHoverEvents(True)


        self.simulation_mode = False

        self.pixmap: QPixmap | None = None
        self.draw_selection = True
        self._visual_offset = QPointF(0, 0)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)


    def add_anchor(self, anchor: AnchorItem):
        existing = self.anchors.get(anchor.name)

        if existing:
            # reaproveita a anchor existente
            existing.setPos(anchor.pos())
            print("Reusing existing anchor", anchor.name)
            return

        anchor.setParentItem(self)
        self.anchors[anchor.name] = anchor

    def remove_anchor(self, name: str):
        anchor = self.anchors.pop(name, None)
        if not anchor:
            return

        print(f"Removing anchor {name}")

        # desconecta conexões que usam essa anchor
        for conn in self.connections[:]:
            if conn.source_anchor == anchor or conn.target_anchor == anchor:
                conn.prepare_delete()

        # remove da cena
        if anchor.scene():
            anchor.scene().removeItem(anchor)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.update_connections()
        return super().itemChange(change, value)
    
    def update_connections(self):
        for conn in self.connections:
            conn.prepareGeometryChange()
            conn.update()

    def prepare_delete(self):
    
        self.connections.clear()


    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter: QPainter, option, widget=None):
        painter.save()  # salva estado atual do painter

        # aplica deslocamento visual (somente para feedback, não afeta anchors)
        painter.translate(self._visual_offset)

        # ícone (se existir)
        if self.pixmap and not self.pixmap.isNull():
            scaled = self.pixmap.scaled(
                self.width,
                self.height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            pos = QPointF(
                (self.width - scaled.width()) / 2,
                (self.height - scaled.height()) / 2
            )
            painter.drawPixmap(pos, scaled)

        # feedback de seleção (bordas, highlight, etc.)
        self.paint_selection_feedback(painter)

        painter.restore()  # restaura estado original, remove o translate

    def getVisualOffset(self):
        return self._visual_offset

    def setVisualOffset(self, value):
        self._visual_offset = value
        self.update()  # força redraw

    visual_offset = pyqtProperty(QPointF, fget=getVisualOffset, fset=setVisualOffset)  

    def apply_preview_constraints(self):
        self.setOpacity(0.5)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.__class__.__name__,
            "position": {
                "x": self.pos().x(),
                "y": self.pos().y()
            },
            "properties": getattr(self, "properties", {})
        }
    
    @classmethod
    def from_dict(cls, data: dict, *, keep_id=True):
        node_cls = cls.registry[data["type"]]
        node = node_cls()

        if keep_id:
            node.id = data["id"]

        pos = data["position"]
        node.setPos(float(pos["x"]), float(pos["y"]))

        node.properties = data.get("properties", {})

        if hasattr(node, "apply_properties"):
            node.apply_properties()

        return node
    
    def update_from_domain(self, domain_node):
        pass

    def reset_visual_state(self):
        """
        Retorna o item gráfico ao estado default (fora de simulação).
        """
        self.simulation_mode = False

        # 🔹 reset visual
        self.visual_offset = QPointF(0, 0)

        if hasattr(self, "initialize_actuators"):
            self.initialize_actuators()

        # 🔹 reset estado do corpo (se existir)
        if hasattr(self, "update_body_visuals"):
            self.body_state = 0
            self.update_body_visuals()

        # 🔹 atualiza anchors dependentes do estado
        if hasattr(self, "update_anchor_positions"):
            self.update_anchor_positions()

        self.update()