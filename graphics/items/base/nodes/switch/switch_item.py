from PyQt6.QtGui import QPixmap, QTransform, QPainterPath, QAction
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QMenu

from graphics.items.base.nodes.node_item import NodeItem
from .....anchors.anchor import AnchorItem
from graphics.labels.label import LabelItem

class SwitchItem(NodeItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.properties = {
            "contact_type": "NO"  # ou "NC"
        }

        self.state = 0  # estado lógico atual (0 ou 1)

        self.initialize_body_visuals()
        self.initialize_anchors()

    def mousePressEvent(self, event):
        if self.simulation_mode:
            if self.shape().contains(event.pos()):
                self.command.emit(self.id, {
                    "type": "switch",
                    "value": 0 if self.state else 1
                })
                event.accept()
                return

        super().mousePressEvent(event)

    def update_from_domain(self, domain_node):
        self.state = domain_node.state
        self.update_visuals()
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

        self.update_visuals()

        # dimensões base
        self.width = self.body_sprite.width()
        self.height = self.body_sprite.height()

    def update_visuals(self):
        contact_type = self.properties["contact_type"]
        state = self.state

        visual = self.body_visuals[contact_type][state]

        self.body_sprite = visual["sprite"]
        self.visual_offset = visual["offset"]

    def extend_context_menu(self, menu: QMenu):
        menu.addSeparator()

        contact_menu = menu.addMenu("Tipo de contato")

        for t in ("NO", "NC"):
            action = QAction(t, menu, checkable=True)
            action.setChecked(self.properties.get("contact_type") == t)
            action.triggered.connect(lambda _, x=t: self.set_contact_type(x))
            contact_menu.addAction(action)

    def set_contact_type(self, contact_type: str):
        if self.properties.get("contact_type") == contact_type:
            return

        self.properties["contact_type"] = contact_type

        # atualiza visual local imediatamente
        self.update_visuals()
        self.update_connections()
        self.update()

    def paint(self, painter, option, widget=None):
        painter.drawPixmap(
            int(self.visual_offset.x()),
            int(self.visual_offset.y()),
            self.body_sprite
        )

        self.paint_selection_feedback(painter)