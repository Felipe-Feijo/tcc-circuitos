from PyQt6.QtWidgets import QGraphicsEllipseItem
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPen, QPainterPath

from graphics.labels.label import LabelItem

class AnchorItem(QGraphicsEllipseItem):
    def __init__(self, name: str, pos: QPointF, radius: float = 6, node=None, domain=None, exit_directions=None, margin=None):
        super().__init__(-radius, -radius, 2 * radius, 2 * radius, node)

        self.name = name
        self.id = (node.id, name)
        self.node = node
        self.domain = domain
        self.hit_radius = radius * 4

        self.exit_directions = exit_directions # Ex: {"external": ["left", "right"], "internal": ["top"]}
        self.margin = margin

        self.setPos(pos)

        self._active = False

        if domain == "hydraulic":
            self.pressure: float = 0.0
            self.flow: float = 0.0
            self._init_hydraulic_labels()

        # aparência inicial: invisível
        self.setBrush(Qt.GlobalColor.transparent)
        self.setPen(QPen(Qt.PenStyle.NoPen))

        # GARANTIAS
        self.setZValue(100)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        r = self.hit_radius
        path.addEllipse(-r, -r, 2 * r, 2 * r)
        return path
    
    def boundingRect(self):
        r = self.hit_radius
        return QRectF(-r, -r, 2 * r, 2 * r)

    def hoverEnterEvent(self, event):

        is_source_anchor = (self.node.editor.view._connecting and self.node.editor.view._conn_source_anchor is self)
        
        if self.node.editor and self.node.editor.mode == "connect" and not is_source_anchor:
            source = self.node.editor.view._conn_source_anchor

            if source and source.domain != self.domain:
                return
            
            self.setBrush(Qt.GlobalColor.red)
            self.node.editor.hover_anchor = self

            self.update()

    def hoverLeaveEvent(self, event):
        if self.node.editor.hover_anchor is self:
            self.node.editor.hover_anchor = None

        is_source_anchor = (self.node.editor.view._connecting and self.node.editor.view._conn_source_anchor is self)

        if not is_source_anchor:
                self.setBrush(Qt.GlobalColor.transparent)
                self.update()

    def set_exit_directions(self, exit_directions: dict):
        self.exit_directions = exit_directions

    def _init_hydraulic_labels(self):
        

        self._label_hydraulic = LabelItem(properties={
            "text": "0.0 Pa | 0.0 m³/s",
            "editable": False,
            "movable": True,
            "border": False,
            "font_size": 8,
        })

        self._label_hydraulic.setParentItem(self.node)
        self._label_hydraulic.setPos(self.pos() + QPointF(10, -8))

    def update_hydraulic_labels(self):
        if not hasattr(self, "_label_hydraulic"):
            return

        if isinstance(self.pressure, str) or isinstance(self.flow, str):
            self._label_hydraulic.set_text("ERR | ERR")
            return

        p = self.format_hydraulic_value(self.pressure, "Pa")
        q = self.format_hydraulic_value(abs(self.flow), "m³/s")
        self._label_hydraulic.set_text(f"{p} | {q}")

    def format_hydraulic_value(self,value: float, unit: str) -> str:
        # trata ruído numérico como zero
        if abs(value) < 1e-10:
            return f"0 {unit}"
        if abs(value) < 0.01 or abs(value) >= 10000:
            return f"{value:.2e} {unit}"
        return f"{value:.3f} {unit}"