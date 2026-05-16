from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtWidgets import QMenu, QHBoxLayout, QLabel, QPushButton, QFrame

from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.node_item import NodeItem
from .....anchors.anchor import AnchorItem
from graphics.utils.properties_dialog import PropertiesDialog

class ExpandableItem(NodeItem):
    def setup(self) -> None:
        self.properties = {
            "anchors": list(getattr(self, "DEFAULT_ANCHORS", []))
        }
        self.spacing = 120
        self.internal_connections = []
        self.anchor_list = []
        self.initialize_terminal_visuals()
        self.initialize_anchors()

    @property
    def MIN_ANCHORS(self):
        return len(self.DEFAULT_ANCHORS)

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
        if len(self.anchor_list) <= self.MIN_ANCHORS:
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
        self.layout_anchors()
        self.rebuild_exit_rules()
        QTimer.singleShot(0, self.update_internal_connections)

    def layout_anchors(self):
        raise NotImplementedError

    def paint(self, painter, option, widget=None):
        self.paint_symbol(painter)
        self.paint_selection_feedback(painter)

    def paint_symbol(self, painter):
        raise NotImplementedError

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

        # passo 2: garante que existe uma conexão para cada par adjacente
        for i in range(len(anchors) - 1):
            a1 = anchors[i]
            a2 = anchors[i + 1]

            if not self._has_internal_connection(a1, a2):
                conn = self._create_internal_connection(a1, a2)
                self.internal_connections.append(conn)

        # passo 3: atualiza visual de todas as conexões
        self.update_connections()


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

    def rebuild_exit_rules(self):
        # Obtém o dicionário de regras da subclasse
        anchor_rules = getattr(self, "ANCHOR_DIRECTIONS", None)
        if not anchor_rules:
            return

        anchors = self.anchor_list
        total_anchors = len(anchors)

        # Caso haja apenas uma anchor, aplicamos as regras de "single"
        if total_anchors == 1:
            single_rules = anchor_rules.get("single", {})
            anchors[0].set_exit_directions(single_rules)
            return

        # Para múltiplas anchors, aplicamos first / middle / last
        for index, anchor in enumerate(anchors):
            if index == 0:
                rules_to_apply = anchor_rules.get("first", {})
            elif index == total_anchors - 1:
                rules_to_apply = anchor_rules.get("last", {})
            else:
                rules_to_apply = anchor_rules.get("middle", {})

            anchor.set_exit_directions(rules_to_apply)

    def build_properties_dialog(node) -> PropertiesDialog:
        dialog = PropertiesDialog(title="Expandable — Properties")

        current_total = len(node.anchor_list)
        min_anchors = node.MIN_ANCHORS

        # estado interno do dialog
        deltas = {"left": 0, "right": 0}

        # --- widgets ---
        def make_counter_row(side: str):
            row = QHBoxLayout()
            row.setSpacing(8)

            label = QLabel(f"{'Esquerda' if side == 'left' else 'Direita'}:")
            label.setFixedWidth(70)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            btn_minus = QPushButton("−")
            btn_minus.setFixedSize(28, 28)

            value_label = QLabel("0")
            value_label.setFixedWidth(28)
            value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            btn_plus = QPushButton("+")
            btn_plus.setFixedSize(28, 28)

            row.addWidget(label)
            row.addWidget(btn_minus)
            row.addWidget(value_label)
            row.addWidget(btn_plus)
            row.addStretch()

            return row, btn_minus, value_label, btn_plus

        row_left, btn_minus_left, val_left, btn_plus_left = make_counter_row("left")
        row_right, btn_minus_right, val_right, btn_plus_right = make_counter_row("right")

        # insere as rows no form layout (via addRow com widget container)
        # como são QHBoxLayout, embrulhamos num QFrame
        def wrap_layout(layout):
            frame = QFrame()
            frame.setLayout(layout)
            return frame

        dialog._form_layout.addRow(wrap_layout(row_left))
        dialog._form_layout.addRow(wrap_layout(row_right))

        def update_buttons():
            dl = deltas["left"]
            dr = deltas["right"]
            total_delta = dl + dr

            # se algum é positivo, bloqueia negativos
            any_positive = dl > 0 or dr > 0
            # se algum é negativo, bloqueia positivos
            any_negative = dl < 0 or dr < 0

            # remoção máxima respeitando MIN_ANCHORS
            max_removable = current_total - min_anchors

            btn_plus_left.setEnabled(not any_negative)
            btn_plus_right.setEnabled(not any_negative)

            btn_minus_left.setEnabled(
                not any_positive and (-total_delta + 1) <= max_removable
            )
            btn_minus_right.setEnabled(
                not any_positive and (-total_delta + 1) <= max_removable
            )

            val_left.setText(str(dl))
            val_right.setText(str(dr))

        def on_plus(side):
            deltas[side] += 1
            update_buttons()

        def on_minus(side):
            deltas[side] -= 1
            update_buttons()

        btn_plus_left.clicked.connect(lambda: on_plus("left"))
        btn_minus_left.clicked.connect(lambda: on_minus("left"))
        btn_plus_right.clicked.connect(lambda: on_plus("right"))
        btn_minus_right.clicked.connect(lambda: on_minus("right"))

        update_buttons()

        # expõe deltas para apply_properties_from_dialog
        dialog._deltas = deltas

        return dialog


    def apply_properties_from_dialog(node, dialog):
        dl = dialog._deltas["left"]
        dr = dialog._deltas["right"]

        if dl > 0:
            for _ in range(dl):
                node.add_anchor_side("left")
        elif dl < 0:
            for _ in range(abs(dl)):
                node.remove_anchor_side("left")

        if dr > 0:
            for _ in range(dr):
                node.add_anchor_side("right")
        elif dr < 0:
            for _ in range(abs(dr)):
                node.remove_anchor_side("right")