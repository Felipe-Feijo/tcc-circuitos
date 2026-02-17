from PyQt6.QtGui import QPixmap, QTransform, QPainterPath, QAction
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QMenu


from graphics.items.base.nodes.node_item import NodeItem
from .....anchors.anchor import AnchorItem
from graphics.labels.label import LabelItem

ACTUATOR_DICT = {
    "button": {
        "label": "Button",
        "sprite_active_path": "resources/actuators/button/button_active.png",
        "sprite_inactive_path": "resources/actuators/button/button_inactive.png",
        "mirrored": True,
        "menu": True,
        "default_bit": 0,
    },
    "spring": {
        "label": "Spring",
        "sprite_active_path": "resources/actuators/spring/spring_active.png",
        "sprite_inactive_path": "resources/actuators/spring/spring_inactive.png",
        "mirrored": True,
        "menu": True,
        "default_bit": 1,
    },
    "pneumatic_pilot": {
        "label": "Pilot (pneumatic)",
        "sprite_active_path": "resources/actuators/pneumatic_pilot/pneumatic_pilot.png",
        "sprite_inactive_path": "resources/actuators/pneumatic_pilot/pneumatic_pilot.png",
        "mirrored": True,
        "menu": True,
        "default_bit": 0,
    },
    "limit_switch": {
        "label": "Limit Switch",
        "sprite_active_path": "resources/actuators/limit_switch/limit_switch_active.png",
        "sprite_inactive_path": "resources/actuators/limit_switch/limit_switch_inactive.png",
        "mirrored": True,
        "menu": False,
        "default_bit": 0,
    },
    "solenoid": {
        "label": "Solenoid (electric)",
        "sprite_active_path": "resources/actuators/solenoid/solenoid.png",
        "sprite_inactive_path": "resources/actuators/solenoid/solenoid.png",
        "mirrored": True,
        "menu": False,
        "default_bit": 0,
    }
}

class DirectionalValveItem(NodeItem):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.properties = {
            "actuators": {
                "left": None,
                "right": None
            }
        }
        if self.sensor_registry:
            self.sensor_registry.sensor_added.connect(self._on_sensor_registry_changed)
            self.sensor_registry.sensor_removed.connect(self._on_sensor_registry_changed)
            self.sensor_registry.sensor_renamed.connect(self._on_sensor_renamed)
        self.actuators = {}
        self.actuator_visuals = {}  # sprites carregados
        self.actuator_rects = {}

        # Bits dos atuadores
        self.bits = {"left": 0, "right": 0}


        self.initialize_body_visuals()
        self.initialize_anchors()
        self.initialize_actuators()

    @property
    def body_rect(self):
        return QRectF(
            self.visual_offset.x(),
            self.visual_offset.y(),
            self.width,
            self.height
        )

    # --------------------------
    # Retângulo delimitador
    # --------------------------
    def boundingRect(self) -> QRectF:
        """Retângulo total incluindo body, atuadores e deslocamento máximo."""
        margin = 10
        body_w, body_h = self.width, self.height

        # se os rects ainda não existirem, usamos tamanho padrão do body ou 0
        left_w = left_h = right_w = right_h = 0

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
        # desenha o corpo
        painter.drawPixmap(
            int(self.visual_offset.x()),
            int(self.visual_offset.y()),
            self.body_sprite
        )

        # desenha atuadores
        for side, rect in self.actuator_rects.items():
            visuals = self.actuator_visuals.get(side)
            if not visuals:
                continue

            sprite = visuals["active"] if self.bits.get(side, 0) else visuals["inactive"]

            painter.drawPixmap(
                int(rect.x() + self.visual_offset.x()),
                int(rect.y() + self.visual_offset.y()),
                sprite
            )

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
                    # ✅ CORRIGIDO: verificar o tipo do atuador
                    actuator = self.actuators.get(side)
                    if not actuator or actuator.get("type") != "button":
                        continue  # só responde a botões
                    
                    # inverte o bit do atuador
                    self.command.emit(self.id, {
                        "type": "actuator",
                        "value": 1 if self.bits[side] == 0 else 0,
                        "side": side
                    })
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

        left_rect = self.actuator_rects.get("left")
        right_rect = self.actuator_rects.get("right")
        if left_rect:
            path.addRect(left_rect.translated(self.visual_offset))
        if right_rect:
            path.addRect(right_rect.translated(self.visual_offset))

        return path
    
    def update_from_domain(self, domain_node):
        self.bits = domain_node.bits.copy()
        self.body_state = domain_node.body_state

        self.update_body_visuals()
        self.update_actuators_visuals()

        self.update_connections()
        self.update()


    def update_body_visuals(self):
        visual = self.body_visuals[self.body_state]

        self.body_sprite = visual["sprite"]
        self.visual_offset = visual["offset"]


    def update_actuators_visuals(self):
        for side in ("left", "right"):
            anchor_name = "PL" if side == "left" else "PR"
            if anchor_name in self.anchors:
                base_x = (
                    self.actuator_rects[side].left()
                    if side == "left"
                    else self.actuator_rects[side].right()
                )

                x = base_x + self.visual_offset.x()
                y = self.height * 0.6222 + self.visual_offset.y()
                self.anchors[anchor_name].setPos(QPointF(x, y))

            # 🔹 mover label do limit switch
            label = self.special_labels.get(f"actuator_label_{side}")
            if label and hasattr(label, "_relative_pos"):
                label.setPos(label._relative_pos + self.visual_offset)

        self.update_connections()
 
    def _load_actuator_pixmaps(self, actuator_desc, side):
        active = QPixmap(actuator_desc["sprite_active_path"])
        inactive = QPixmap(actuator_desc["sprite_inactive_path"])

        if side == "right" and actuator_desc.get("mirrored", False):
            active = active.transformed(QTransform().scale(-1, 1))
            inactive = inactive.transformed(QTransform().scale(-1, 1))

        return {"active": active, "inactive": inactive}

    def initialize_body_visuals(self):
        self.body_visuals = {
            state: {
                "sprite": QPixmap(desc["sprite"]),
                "offset": desc["offset"]
            }
            for state, desc in self.BODY_VISUALS.items()
        }
        self.max_offset_x = max(
            visual["offset"].x()
            for visual in self.body_visuals.values()
        )

        self.body_state = 0
        self.body_sprite = self.body_visuals[0]["sprite"]
        self.visual_offset = self.body_visuals[0]["offset"]

        # Dimensões do body
        self.width = self.body_sprite.width()
        self.height = self.body_sprite.height()

    def initialize_anchors(self):
        pass

    def initialize_actuators(self):
        """
        Reconfigura completamente os atuadores da válvula.
        Pode ser chamado múltiplas vezes.
        """

        self.actuator_visuals.clear()
        self.actuator_rects.clear()

        body = self.body_rect

        self.actuators = self.properties["actuators"]

        for side in ("left", "right"):
            
            self.remove_label(f"actuator_label_{side}", special=True)
            actuator_cfg = self.actuators.get(side)
            if not actuator_cfg:
                actuator_name = None
                sensor_name = None
            else:
                actuator_name = actuator_cfg["type"]
                sensor_name = actuator_cfg.get("sensor_name")
            actuator_desc = ACTUATOR_DICT.get(actuator_name)

            anchor_name = "PL" if side == "left" else "PR"
            if not actuator_desc:
                self.remove_anchor(anchor_name)
                continue

            # 🔹 estado visual inicial coerente
            if not self.simulation_mode:
                default_bit = actuator_desc.get("default_bit")
                if default_bit is not None:
                    self.bits[side] = default_bit

            # carregar visuais
            visuals = self._load_actuator_pixmaps(actuator_desc, side)
            self.actuator_visuals[side] = visuals

            # calcular rect
            pix = visuals["active"]
            w, h = pix.width(), pix.height()

            if side == "left":
                x = body.left() - w
            else:
                x = body.right()

            y = body.center().y() - h / 2

            self.actuator_rects[side] = QRectF(x, y, w, h)

            
            if actuator_name == "pneumatic_pilot":
                x = self.actuator_rects[side].left() if side == "left" else self.actuator_rects[side].right()
                self.add_anchor(AnchorItem(anchor_name, QPointF(x, self.height*0.6222), node=self, domain='pneumatic', exit_directions={"external": ["left"] if side == "left" else ["right"]})) 
            else:
                # se não é pilot, garante que não exista
                self.remove_anchor(anchor_name)

            label_name = f"actuator_label_{side}"

            # remove label antiga por segurança
            self.remove_label(label_name, special=True)

            if actuator_name in ["limit_switch", "solenoid"] and sensor_name:
                rect = self.actuator_rects[side]
                

                # posição relativa ao sprite
                label_x = rect.x() +  rect.width() * (0.42 if side == "left" else 0.18)
                label_y = rect.y() + rect.height() * 0.25

                label = LabelItem(
                    properties={
                        "text": sensor_name,
                        "editable": False,
                        "movable": False,
                        "max_length": 3,
                        "on_commit": lambda t, s=side: self._set_actuator_sensor_name(s, t),
                        "border": True,
                    }
                )

                relative_pos = QPointF(label_x, label_y)

                label._relative_pos = relative_pos
                label.setPos(relative_pos + self.visual_offset)

                self.add_label(label_name, label, special=True)


    def apply_properties(self):
        self.initialize_actuators()
        self.update()

    def extend_context_menu(self, menu: QMenu):
        super().extend_context_menu(menu)
        menu.addSeparator()

        left_menu = menu.addMenu("Atuador esquerdo")
        right_menu = menu.addMenu("Atuador direito")

        self._populate_actuator_menu(left_menu, side="left")
        self._populate_actuator_menu(right_menu, side="right")

        

    def _populate_actuator_menu(self, menu: QMenu, side: str):
        current = self.actuators.get(side)

        # -----------------------
        # Opção "Nenhum"
        # -----------------------
        action_none = QAction("None", menu, checkable=True)
        action_none.setChecked(current is None)
        action_none.triggered.connect(
            lambda _, s=side: self.set_actuator(s, None)
        )
        menu.addAction(action_none)
        menu.addSeparator()

        # -----------------------
        # Atuadores do ACTUATOR_DICT
        # -----------------------
        for name, desc in ACTUATOR_DICT.items():
            if not desc.get("menu", True):
                continue
            action = QAction(desc["label"], menu, checkable=True)
            action.setChecked(current is not None and current.get("type") == name)
            action.triggered.connect(
                lambda _, s=side, n=name: self.set_actuator(s, n)
            )
            menu.addAction(action)

        # -----------------------
        # Sensores de cilindro (limit_switch)
        # -----------------------
        if self.sensor_registry:
            cylinder_signals = self.sensor_registry.list_names(sensor_type="cylinder_end")
            if cylinder_signals:
                menu.addSeparator()
                for sensor_name in cylinder_signals:
                    action = QAction(sensor_name, menu, checkable=True)
                    is_checked = (
                        current is not None
                        and current.get("type") == "limit_switch"
                        and current.get("sensor_name") == sensor_name
                    )
                    action.setChecked(is_checked)
                    action.triggered.connect(
                        lambda _, s=side, n=sensor_name: self.set_actuator(s, "limit_switch", n)
                    )
                    menu.addAction(action)

            # -----------------------
            # Sensores elétricos (solenoid)
            # -----------------------
            electric_signals = self.sensor_registry.list_names(sensor_type="solenoid_coil")
            if electric_signals:
                menu.addSeparator()
                for sensor_name in electric_signals:
                    action = QAction(sensor_name, menu, checkable=True)
                    # marca como selecionado se este sensor for do tipo solenoid
                    is_checked = (
                        current is not None
                        and current.get("type") == "solenoid"
                        and current.get("sensor_name") == sensor_name
                    )
                    action.setChecked(is_checked)
                    action.triggered.connect(
                        lambda _, s=side, n=sensor_name: self.set_actuator(s, "solenoid", n)
                    )
                    menu.addAction(action)

    def set_actuator(self, side: str, actuator_name: str | None, actuator_sensor_name: str | None = None,):
        current = self.properties["actuators"].get(side)

        if actuator_name is None:
            new_value = None
        elif actuator_name in ["limit_switch", "solenoid"]:
            new_value = {
                "type": actuator_name,
                "sensor_name": actuator_sensor_name,
            }
        else:
            new_value = {
                "type": actuator_name
            }

        if current == new_value:
            return

        self.properties["actuators"][side] = new_value

        self.prepareGeometryChange()
        self.initialize_actuators()
        self.update()


    def _set_actuator_sensor_name(self, side: str, new_name: str):
        actuator = self.properties["actuators"].get(side)
        if not actuator or actuator.get("type") not in ["limit_switch", "solenoid"]:
            return

        old_name = actuator.get("sensor_name")

        if not new_name or new_name == old_name:
            return

        # valida existência no registry
        if self.sensor_registry and not self.sensor_registry.exists(new_name):
            # volta ao antigo
            label = self.special_labels.get(f"actuator_label_{side}")
            if label:
                label.set_text(old_name or "")
            return

        actuator["sensor_name"] = new_name

    def _on_sensor_registry_changed(self, *args):
        changed = False

        for side in ("left", "right"):
            actuator = self.properties["actuators"].get(side)
            if not actuator or actuator.get("type") not in ["limit_switch", "solenoid"]:
                continue

            sensor_name = actuator.get("sensor_name")
            if not sensor_name:
                continue

            if not self.sensor_registry.exists(sensor_name):
                # sensor sumiu → desassocia
                self.properties["actuators"][side] = None
                changed = True

        if changed:
            self.initialize_actuators()
            self.update()

    def _on_sensor_renamed(self, old_name, new_name, node):
        updated = False

        for side in ("left", "right"):
            actuator = self.properties["actuators"].get(side)
            if not actuator or actuator.get("type") not in ["limit_switch", "solenoid"]:
                continue

            if actuator.get("sensor_name") == old_name:
                actuator["sensor_name"] = new_name

                label = self.special_labels.get(f"actuator_label_{side}")
                if label:
                    label.set_text(new_name)

                updated = True

        if updated:
            self.update()

