from PyQt6.QtWidgets import QGraphicsEllipseItem
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPen, QBrush

class AnchorItem(QGraphicsEllipseItem):
    def __init__(self, name: str, pos: QPointF, radius: float = 6, node=None,):
        super().__init__(-radius, -radius, 2 * radius, 2 * radius, node)

        self.name = name
        self.id = name
        self.node = node
        self.radius = radius

        self.setPos(pos)

        self._active = False


        # aparência inicial: invisível
        self.setBrush(Qt.GlobalColor.transparent)
        self.setPen(QPen(Qt.PenStyle.NoPen))

        # GARANTIAS
        self.setZValue(100)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def hoverEnterEvent(self, event):

        is_source_anchor = (self.node.editor.view._connecting and self.node.editor.view._conn_source_anchor is self)
        
        if self.node.editor and self.node.editor.mode == "connect" and not is_source_anchor:
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