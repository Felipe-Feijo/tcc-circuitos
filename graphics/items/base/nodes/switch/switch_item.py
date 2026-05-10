from PyQt6.QtGui import QPixmap, QTransform, QPainterPath, QAction
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QMenu

from graphics.items.base.nodes.node_item import NodeItem
from .....anchors.anchor import AnchorItem
from graphics.labels.label import LabelItem

class SwitchItem(NodeItem):
    def setup(self) -> None:
        self.properties = {"contact_type": "NO"}
        self.body_state = 0
        self.initialize_body_visuals()
        self.initialize_anchors()

    def update_from_domain(self, domain_node):
        super().update_from_domain(domain_node)
        self.body_state = domain_node.state
        self.update_body_visuals()
        self.update_connections()
        self.update()

    def initialize_body_visuals(self):
        self.body_visuals = {
            contact_type: {
                state: {
                    "sprite": QPixmap(desc["sprite"]),
                    "offset": desc.get("offset", QPointF(0, 0))
                }
                for state, desc in states.items()
            }
            for contact_type, states in self.SWITCH_VISUALS.items()
        }

        self.max_offset_x = max(
            visual["offset"].x()
            for ct in self.body_visuals.values()
            for visual in ct.values()
        )

        self.update_body_visuals()

        # dimensões base
        self.width = self.body_sprite.width()
        self.height = self.body_sprite.height()

    def update_body_visuals(self):
        contact_type = self.properties["contact_type"]
        state = self.body_state

        visual = self.body_visuals[contact_type][state]

        self.body_sprite = visual["sprite"]
        self.visual_offset = visual["offset"]

    def mousePressEvent(self, event) -> None:
        """Toggle switch state on click in simulation mode."""
        from PyQt6.QtCore import Qt
        if self.simulation_mode and event.button() == Qt.MouseButton.LeftButton:
            new_state = 0 if self.body_state else 1
            self.command.emit(self.id, {"type": "switch", "value": new_state})
            event.accept()
            return
        super().mousePressEvent(event)

    def extend_context_menu(self, menu: QMenu):
        menu.addSeparator()

        contact_menu = menu.addMenu("Tipo de contato")

        for t in ("NO", "NC"):
            action = QAction(t, menu, checkable=True)
            action.setChecked(self.properties.get("contact_type") == t)
            action.triggered.connect(lambda _, x=t: self.set_contact_type(x))
            contact_menu.addAction(action)

        super().extend_context_menu(menu)

    def set_contact_type(self, contact_type: str):
        if self.properties.get("contact_type") == contact_type:
            return

        self.properties["contact_type"] = contact_type

        # atualiza visual local imediatamente
        self.update_body_visuals()
        self.update_connections()
        self.update()

    def paint(self, painter, option, widget=None):
        self.draw_pixmap(painter, QPointF(int(self.visual_offset.x()), int(self.visual_offset.y())), self.body_sprite)

        self.paint_selection_feedback(painter)

    def apply_properties(self):
        self.update_body_visuals()
        self.update()

    def boundingRect(self) -> QRectF:
        margin = 10

        body_w = self.width
        body_h = self.height

        leftmost_x = -margin
        total_width = body_w + self.max_offset_x + 2 * margin

        top_y = -margin
        total_height = body_h + 2 * margin

        return QRectF(leftmost_x, top_y, total_width, total_height)
    
    def shape(self):
        path = QPainterPath()

        body_rect = QRectF(
            self.visual_offset.x(),
            self.visual_offset.y(),
            self.width,
            self.height
        )

        path.addRect(body_rect)
        return path

