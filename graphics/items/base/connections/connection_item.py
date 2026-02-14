# graphics/items/connection_item.py
from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtGui import QPainterPath, QPen, QPainter, QPainterPathStroker
from PyQt6.QtCore import Qt, QPointF, QRectF
from graphics.items.base.diagram_item_base import DiagramItemBase


class ConnectionItem(DiagramItemBase):
    def __init__(self, source_node, source_anchor, target_node=None, target_anchor=None):
        DiagramItemBase.__init__(self)

        self.state: float = 0.0  # 0 = desligado, 1 = ligado (pneumatic/electric), 0-1 contínuo (hidraulic)

        self.id = frozenset([
            source_anchor.id,
            target_anchor.id if target_anchor else None
        ])

        self.source = source_node
        self.source_anchor = source_anchor
        self.target = target_node
        self.target_anchor = target_anchor

        self.temp_target_pos = None

        self.setPos(0, 0)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        # Pens para cada domínio
        if self.domain == "pneumatic":
            self.pen = QPen(Qt.GlobalColor.red, 3)
        elif self.domain == "electric":
            self.pen = QPen(Qt.GlobalColor.white, 3)
        elif self.domain == "hydraulic":
            # ainda placeholder
            self.pen = QPen(Qt.GlobalColor.cyan, 3)
        
        self.setZValue(-10)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.update()

    @property
    def domain(self):
        return getattr(self.source_anchor, "domain")

    def shape(self) -> QPainterPath:
        """Define a área clicável/selecionável seguindo o caminho da linha"""
        path = QPainterPath()
        points = self.get_path_points()
        
        if len(points) < 2:
            return path
        
        # Cria um "stroke" ao redor da linha para facilitar seleção
        line_path = QPainterPath()
        line_path.moveTo(points[0])
        for point in points[1:]:
            line_path.lineTo(point)
        
        # Cria uma área de 8px ao redor da linha (facilita clique/seleção)
        stroker = QPainterPathStroker()
        stroker.setWidth(8)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        
        return stroker.createStroke(line_path)
    

    def boundingRect(self) -> QRectF:
        
        points = self.get_path_points()
        if len(points) < 2:
            return QRectF()

        margin = 10
        min_x = min(p.x() for p in points)
        max_x = max(p.x() for p in points)
        min_y = min(p.y() for p in points)
        max_y = max(p.y() for p in points)

        return QRectF(
            min_x - margin,
            min_y - margin,
            max_x - min_x + 2 * margin,
            max_y - min_y + 2 * margin
        )

    def paint(self, painter: QPainter, option, widget=None):
        points = self.get_path_points()
        if len(points) < 2:
            return

        # Seleção tem prioridade
        if self.isSelected():
            pen = QPen(Qt.GlobalColor.blue, 3)
        else:
            # cores por domínio
            if self.domain == "pneumatic" and self.state == 1:
                pen = QPen(Qt.GlobalColor.green, 3)
            elif self.domain == "electric" and self.state == 1:
                pen = QPen(Qt.GlobalColor.yellow, 3)
            elif self.domain == "hydraulic" and self.state == 1:
                # ainda placeholder
                pen = QPen(Qt.GlobalColor.cyan, 3)
            else:
                pen = self.pen

        painter.setPen(pen)
        
        for start, end in zip(points, points[1:]):
            painter.drawLine(start, end)


    def get_path_points(self) -> list[QPointF]:
    
        if not self.source_anchor:
            return []

        p1 = self.source_anchor.scenePos()

        if self.target_anchor:
            p2 = self.target_anchor.scenePos()
        elif self.temp_target_pos:
            p2 = self.temp_target_pos
        else:
            return [p1]

        mid_y = (p1.y() + p2.y()) / 2
        return [
            p1,
            QPointF(p1.x(), mid_y),
            QPointF(p2.x(), mid_y),
            p2
        ]

    def update_temp_endpoint(self, scene_pos):
        """Atualiza endpoint temporário garantindo atualização correta da área"""
        self.prepareGeometryChange()
        self.temp_target_pos = scene_pos
        self.update()

    def update_position(self):
        """Chamado quando nós conectados se movem"""
        self.prepareGeometryChange()
        self.update()

    def itemChange(self, change, value):
        """Detecta mudanças e força atualização adequada"""
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            # Quando seleção muda, apenas repinta com a cor correta
            self.update()
        
        return super().itemChange(change, value)

    def prepare_delete(self):

        # desconecta dos nodes (lógico)
        if self.source and self in self.source.connections:
            self.source.connections.remove(self)

        if self.target and self in self.target.connections:
            self.target.connections.remove(self)

        self.source = None
        self.target = None

        self.prepareGeometryChange()

    def to_dict(self):
        return {
            "source": {
                "node": self.source.id,
                "anchor": self.source_anchor.name
            },
            "target": {
                "node": self.target.id,
                "anchor": self.target_anchor.name
            }
        }
    
    @classmethod
    def from_dict(cls, data: dict, node_index: dict):
        source_data = data["source"]
        target_data = data["target"]

        source_node = node_index[source_data["node"]]
        target_node = node_index[target_data["node"]]

        source_anchor = source_node.anchors[source_data["anchor"]]
        target_anchor = target_node.anchors[target_data["anchor"]]

        conn = cls(source_node, source_anchor, target_node, target_anchor)

        source_node.connections.append(conn)
        target_node.connections.append(conn)
        return conn
    

    def set_state(self, value: float):
        """
        Atualiza o estado da connection e repinta de acordo com domínio.
        """
        if self.state != value:
            self.state = value
            self.update()

    def reset_visual_state(self):
        """Retorna a connection ao estado neutro fora de simulação"""
        self.state = 0
        self.update()