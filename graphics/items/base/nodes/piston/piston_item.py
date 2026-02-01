from PyQt6.QtGui import QPixmap, QPainterPath
from PyQt6.QtCore import QRectF, QPointF

from graphics.items.base.nodes.node_item import NodeItem
from .....anchors.anchor import AnchorItem


class PistonItem(NodeItem):
    """
    Classe base para todos os pistões.
    A subclasse deve definir BODY_VISUALS.
    """

    BODY_VISUALS = {}  # definido pela subclasse

    def __init__(self):
        super().__init__()

        if not self.BODY_VISUALS:
            raise RuntimeError("PistonItem subclasses must define BODY_VISUALS")

        self.body_visuals = {}
        self.body_state = 0
        self.body_sprite = None
        self.visual_offset = QPointF(0, 0)

        self.initialize_body_visuals()
        self.initialize_anchors()

    # --------------------------
    # Inicialização
    # --------------------------
    def initialize_body_visuals(self):
        self.body_visuals = {
            state: {
                "sprite": QPixmap(desc["sprite"]),
                "offset": desc.get("offset", QPointF(0, 0))
            }
            for state, desc in self.BODY_VISUALS.items()
        }

        # estado inicial
        self.body_state = min(self.body_visuals.keys())
        visual = self.body_visuals[self.body_state]

        self.body_sprite = visual["sprite"]
        self.visual_offset = visual["offset"]

        self.width = self.body_sprite.width()
        self.height = self.body_sprite.height()

    def initialize_anchors(self):
        pass

    # --------------------------
    # Geometria
    # --------------------------
    @property
    def body_rect(self):
        return QRectF(
            self.visual_offset.x(),
            self.visual_offset.y(),
            self.width,
            self.height
        )

    def boundingRect(self) -> QRectF:
        margin = 10
        rect = self.body_rect
        return rect.adjusted(-margin, -margin, margin, margin)

    def shape(self):
        path = QPainterPath()
        path.addRect(self.body_rect)
        return path

    # --------------------------
    # Desenho
    # --------------------------
    def paint(self, painter, option, widget=None):
        painter.drawPixmap(
            int(self.visual_offset.x()),
            int(self.visual_offset.y()),
            self.body_sprite
        )

        self.paint_selection_feedback(painter)

    # --------------------------
    # Atualização de estado
    # --------------------------
    def update_from_domain(self, domain_node):
        """
        Espera-se que o domain_node exponha
        um estado visual inteiro (ex: 0 ou 1).
        """
        new_state = domain_node.get_visual_state()

        if new_state == self.body_state:
            return

        self.body_state = new_state
        self.update_body_visuals()

        self.update_connections()
        self.update()

    def update_body_visuals(self):
        visual = self.body_visuals.get(self.body_state)
        if not visual:
            return

        self.body_sprite = visual["sprite"]
        self.visual_offset = visual["offset"]
