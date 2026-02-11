from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtWidgets import QMenu

from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.node_item import NodeItem
from .....anchors.anchor import AnchorItem

class ExpandableItem(NodeItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.properties = {
            "anchors": ["X1", "X2"]
        }

        self.initialize_terminal_visuals()

        self.spacing = 120
        self.internal_connections = []

        self.anchor_list = []

        self.initialize_anchors()

    def add_anchor_side(self, side: str):
        anchor = self._create_anchor(side)
        if side == "left":
            self.setX(self.x() - self.spacing)
            self.properties["anchors"].insert(0, anchor.name)
        else:
            self.properties["anchors"].append(anchor.name)
        self.update_layout()
        return anchor
    
    def _create_anchor(self, side: str):
        name = self._next_anchor_name()

        anchor = AnchorItem(
            name,
            QPointF(0, 0),
            node=self,
            domain=self.domain
        )

        self.add_anchor(anchor)

        if side == "left":
            self.anchor_list.insert(0, anchor)
        else:
            self.anchor_list.append(anchor)

        return anchor
    
    def remove_anchor_side(self, side: str):
        if len(self.anchor_list) <= 2:
            return

        # remove da lista lógica primeiro
        if side == "left":
            removed = self.anchor_list.pop(0)
            self.setX(self.x() + self.spacing)
        else:
            removed = self.anchor_list.pop()

        # 👉 REBIND ANTES DE DESTRUIR
        self.update_internal_connections()

        # agora é seguro remover fisicamente
        self.remove_anchor(removed.name)

        # propriedades
        if removed.name in self.properties["anchors"]:
            self.properties["anchors"].remove(removed.name)

        # layout e conexões
        self.update_layout()
        self.update_connections()

    def update_layout(self):
        self.prepareGeometryChange()

        x0 = self.pix_w * 0.5
        y0 = self.pix_h

        for i, anchor in enumerate(self.anchor_list):
            br = anchor.boundingRect()

            cx = x0 + i * self.spacing
            cy = y0

            anchor.setPos(
                cx - br.center().x(),
                cy - br.center().y()
            )
        QTimer.singleShot(0, self.update_internal_connections)

    def paint(self, painter, option, widget=None):
        if not self.pixmap_left or not self.pixmap_right:
            return

        # esquerdo
        painter.drawPixmap(0, 0, self.pixmap_left)

        # direito
        n = len(self.anchor_list)
        last_anchor_center = self.pix_w * 0.5 + (n - 1) * self.spacing
        pixmap_right_x = last_anchor_center - self.pix_w * 0.5

        painter.drawPixmap(int(pixmap_right_x), 0, self.pixmap_right)

        self.paint_selection_feedback(painter)

    def boundingRect(self):
        n = len(self.anchor_list)

        width = (n - 1) * self.spacing + self.pix_w
        height = self.pix_h

        return QRectF(0, 0, width, height)
    
    def extend_context_menu(self, menu: QMenu):
        menu.addSeparator()

        add_menu = menu.addMenu("Adicionar")
        add_menu.addAction("À esquerda", lambda: self.add_anchor_side("left"))
        add_menu.addAction("À direita", lambda: self.add_anchor_side("right"))

        rem_menu = menu.addMenu("Remover")
        rem_menu.addAction("À esquerda", lambda: self.remove_anchor_side("left"))
        rem_menu.addAction("À direita", lambda: self.remove_anchor_side("right"))


    def update_internal_connections(self):
        if getattr(self, "is_preview", False):
            return

        if not self.scene():
            QTimer.singleShot(0, self.update_internal_connections)
            return

        anchors = self.anchor_list

        if len(anchors) < 2:
            return

        # garante que existe uma conexão para cada par adjacente
        for i in range(len(anchors) - 1):
            a1 = anchors[i]
            a2 = anchors[i + 1]

            if not self._has_internal_connection(a1, a2):
                conn = self._create_internal_connection(a1, a2)
                self.internal_connections.append(conn)

        # atualiza posição de todas
        self.update_connections()
        print(self.internal_connections)


    def _has_internal_connection(self, a1, a2):
        for conn in self.internal_connections:
            if conn.source_anchor == a1 and conn.target_anchor == a2:
                return True
            if conn.source_anchor == a2 and conn.target_anchor == a1:
                return True
        return False
    
    def _create_internal_connection(self, a1, a2):
        conn = ConnectionItem(self, a1, self, a2)

        conn.setZValue(-20)
        conn.setFlag(conn.GraphicsItemFlag.ItemIsSelectable, False)
        conn.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        if self.scene():
            self.scene().addItem(conn)

        self.connections.append(conn)
        return conn

    def _next_anchor_name(self):
        i = 1
        existing = {a.name for a in self.anchor_list}
        while f"X{i}" in existing:
            i += 1
        return f"X{i}"
    
    def initialize_anchors(self):
        for anchor in list(self.anchor_list):
            self.remove_anchor(anchor.name)

        self.anchor_list.clear()

        for name in self.properties.get("anchors", []):
            anchor = AnchorItem(
                name,
                QPointF(0, 0),
                node=self,
                domain=self.domain
            )
            self.add_anchor(anchor)
            self.anchor_list.append(anchor)

        self.update_layout()

    def apply_properties(self):
        self.initialize_anchors()
        self.update()

    def initialize_terminal_visuals(self):
        left_path = self.TERMINAL_VISUALS.get("left")
        right_path = self.TERMINAL_VISUALS.get("right")

        self.pixmap_left = QPixmap(left_path) if left_path else None
        self.pixmap_right = QPixmap(right_path) if right_path else None

        if self.pixmap_left:
            self.pix_w = self.pixmap_left.width()
            self.pix_h = self.pixmap_left.height()
        else:
            self.pix_w = 0
            self.pix_h = 0