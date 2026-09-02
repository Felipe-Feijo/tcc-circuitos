"""Base class for directional valves with configurable actuator support."""

from PyQt6.QtGui import QPixmap, QTransform, QPainterPath, QAction
from PyQt6.QtCore import QPointF, QRectF, Qt, QCoreApplication
from PyQt6.QtWidgets import QMenu


from graphics.items.base.nodes.node_item import NodeItem, THREE_POSITION_SIDE_MAP
from graphics.utils.properties_dialog import PropertiesDialog
from graphics.utils.defect_dialog import DefectDialog
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
        # Two behaviors, same actuator: "latch" toggles on click (today's
        # default, kept for backwards compatibility with saved circuits);
        # "momentary" is active only while held (press = 1, release = 0).
        "modes": {
            "latch": {
                "sprite_active_path": "resources/actuators/button/button_latch_active.png",
                "sprite_inactive_path": "resources/actuators/button/button_latch_inactive.png",
            },
            "momentary": {
                "sprite_active_path": "resources/actuators/button/button_active.png",
                "sprite_inactive_path": "resources/actuators/button/button_inactive.png",
            },
        },
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
        "label": "Pilot (Pneumatic)",
        "sprite_active_path": "resources/actuators/pilot/pilot.png",
        "sprite_inactive_path": "resources/actuators/pilot/pilot.png",
        "mirrored": True,
        "menu": True,
        "default_bit": 0,
    },
    "hydraulic_pilot": {
        "label": "Pilot (Hydraulic)",
        "sprite_active_path": "resources/actuators/pilot/pilot.png",
        "sprite_inactive_path": "resources/actuators/pilot/pilot.png",
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
    },
    "timer": {
        "label": "Timer",
        "sprite_active_path": "resources/actuators/timer/timer.png",
        "sprite_inactive_path": "resources/actuators/timer/timer.png",
        "mirrored": True,
        "menu": True,
        "default_bit": 0,
    }
}

SPRING_SCALE = 0.5  # ~50% reduction relative to the "spring" actuator's normal sprite

DEFAULT_BUTTON_MODE = "momentary"  # active only while held; latch is opt-in

class DirectionalValveItem(NodeItem):

    THREE_POSITION = False

    def setup(self) -> None:
        self.properties = {
            "actuators": {"left": None, "right": None},
            # "right" = body_state 0, "left" = body_state 1 (2-position);
            # "right"/"center"/"left" = body_state 0/1/2 (3-position)
            "default_side": "center" if self.THREE_POSITION else "right",
        }
        # k has no default -- required if the domain is hydraulic

        self.actuators = {}
        self.actuator_visuals = {}
        self.actuator_rects = {}
        self.bits = {"left": 0, "right": 0}
        self.spring_visuals = {}
        self.spring_rects = {}
        self._active_momentary_side = None  # side currently held down (momentary button)

        self.initialize_body_visuals()
        self.initialize_anchors()
        self.initialize_actuators()

    def register_sensors(self) -> None:
        # Connect to sensor registry for solenoid actuator name updates
        if self.sensor_registry:
            self.sensor_registry.sensor_added.connect(self._on_sensor_registry_changed)
            self.sensor_registry.sensor_removed.connect(self._on_sensor_registry_changed)
            self.sensor_registry.sensor_renamed.connect(self._on_sensor_renamed)

    @property
    def body_rect(self):
        return QRectF(
            self.visual_offset.x(),
            self.visual_offset.y(),
            self.width,
            self.height
        )

    # --------------------------
    # Bounding rectangle
    # --------------------------
    def boundingRect(self) -> QRectF:
        """Total rectangle including the body, actuators and maximum shift."""
        margin = 10
        body_w, body_h = self.width, self.height

        # if the rects don't exist yet, use the body's default size or 0
        left_w = left_h = right_w = right_h = 0

        left_rect = self.actuator_rects.get("left")
        if left_rect:
            left_w, left_h = left_rect.width(), left_rect.height()
        right_rect = self.actuator_rects.get("right")
        if right_rect:
            right_w, right_h = right_rect.width(), right_rect.height()

        # Some states (e.g. Valve_4_3_Ways, offset relative to the center)
        # have a negative offset -- the body is painted left of x=0 in
        # those cases, so the rectangle needs to extend that far too.
        min_offset_x = min(0, getattr(self, "min_offset_x", 0))
        leftmost_x = min_offset_x - left_w - margin
        total_width = body_w + left_w + right_w + getattr(self, "max_offset_x", 0) - min_offset_x + 2*margin

        # Centering springs can extend above the body's top -- the
        # bounding rect needs to cover that extension, otherwise Qt
        # leaves repaint artifacts outside the declared area.
        spring_top_extent = 0.0
        for rect in self.spring_rects.values():
            spring_top_extent = max(spring_top_extent, -rect.top())

        top_margin = max(0, (left_h - body_h)/2, (right_h - body_h)/2, spring_top_extent)
        bottom_margin = max(0, (right_h - body_h)/2)
        top_y = -top_margin - margin
        total_height = body_h + top_margin + bottom_margin + 2*margin

        return QRectF(leftmost_x, top_y, total_width, total_height)


    # --------------------------
    # Desenho
    # --------------------------
    def paint(self, painter, option, widget=None):
        # desenha o corpo
        self.draw_pixmap(painter, QPointF(int(self.visual_offset.x()), int(self.visual_offset.y()),), self.body_sprite)

        # desenha atuadores
        for side, rect in self.actuator_rects.items():
            visuals = self.actuator_visuals.get(side)
            if not visuals:
                continue

            sprite = visuals["active"] if self.bits.get(side, 0) else visuals["inactive"]

            self.draw_pixmap(painter, QPointF(int(rect.x() + self.visual_offset.x()), int(rect.y() + self.visual_offset.y()),), sprite)

        # draws centering springs (always present on 3-position valves)
        for side, rect in self.spring_rects.items():
            sprite = self._spring_pixmap_for(side)
            if sprite is None:
                continue
            self.draw_pixmap(painter, QPointF(int(rect.x() + self.visual_offset.x()), int(rect.y() + self.visual_offset.y()),), sprite)

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
                    # checks the actuator's type
                    actuator = self.actuators.get(side)
                    if not actuator or actuator.get("type") != "button":
                        continue  # only responds to buttons

                    if actuator.get("mode", DEFAULT_BUTTON_MODE) == "momentary":
                        # active only while held: press -> 1, release -> 0
                        self._active_momentary_side = side
                        self.command.emit(self.id, {
                            "type": "actuator",
                            "value": 1,
                            "side": side
                        })
                    else:
                        # inverte o bit do atuador
                        self.command.emit(self.id, {
                            "type": "actuator",
                            "value": 1 if self.bits[side] == 0 else 0,
                            "side": side
                        })
                    event.accept()
                    return

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        side = self._active_momentary_side
        if side is not None:
            self._active_momentary_side = None
            self.command.emit(self.id, {
                "type": "actuator",
                "value": 0,
                "side": side
            })
            event.accept()
            return

        super().mouseReleaseEvent(event)


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
        super().update_from_domain(domain_node)
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
 
    def _load_actuator_pixmaps(self, actuator_desc, side, mode=None):
        # Actuators with per-mode sprites (currently just "button") pick
        # their sprite pair from "modes"; everything else uses the
        # top-level path unchanged.
        paths = actuator_desc.get("modes", {}).get(mode or DEFAULT_BUTTON_MODE, actuator_desc)

        active = QPixmap(paths["sprite_active_path"])
        inactive = QPixmap(paths["sprite_inactive_path"])

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
        offsets_x = [visual["offset"].x() for visual in self.body_visuals.values()]
        self.max_offset_x = max(offsets_x)
        self.min_offset_x = min(offsets_x)

        if self.THREE_POSITION:
            default_side = self.properties.get("default_side", "center")
            self.body_state = THREE_POSITION_SIDE_MAP.get(default_side, 1)
        else:
            default_side = self.properties.get("default_side", "right")
            self.body_state = 1 if default_side == "left" else 0
        self.body_sprite = self.body_visuals[self.body_state]["sprite"]
        self.visual_offset = self.body_visuals[self.body_state]["offset"]

        # Body dimensions
        self.width = self.body_sprite.width()
        self.height = self.body_sprite.height()

    def initialize_anchors(self):
        pass

    def initialize_actuators(self):
        """
        Fully reconfigures the valve's actuators.
        Can be called multiple times.
        """

        self.actuator_visuals.clear()
        self.actuator_rects.clear()

        body = QRectF(0, 0, self.width, self.height)

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
            actuator_mode = actuator_cfg.get("mode") if actuator_cfg else None
            visuals = self._load_actuator_pixmaps(actuator_desc, side, mode=actuator_mode)
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

            
            if actuator_name in ("pneumatic_pilot", "hydraulic_pilot", "timer"):
                x = self.actuator_rects[side].left() if side == "left" else self.actuator_rects[side].right()
                if actuator_name == "hydraulic_pilot":
                    anchor_domain = "hydraulic"
                elif actuator_name == "pneumatic_pilot":
                    anchor_domain = "pneumatic"
                else:
                    anchor_domain = self.domain
                self.add_anchor(AnchorItem(anchor_name, QPointF(x, self.height*0.6222), node=self, domain=anchor_domain, exit_directions={"external": ["left"] if side == "left" else ["right"]})) 
            else:
                # if it's not a pilot/timer, make sure it doesn't exist
                self.remove_anchor(anchor_name)

            label_name = f"actuator_label_{side}"

            # removes any old label, just in case
            self.remove_label(label_name, special=True)

            if actuator_name in ["limit_switch", "solenoid"] and sensor_name:
                rect = self.actuator_rects[side]
                

                # position relative to the sprite
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

        self._initialize_spring_visuals(body)

    def _initialize_spring_visuals(self, body: QRectF) -> None:
        """Centering spring: always present on both sides of a
        3-position valve, never a real selectable actuator."""
        self.spring_visuals.clear()
        self.spring_rects.clear()

        if not self.THREE_POSITION:
            return

        spring_desc = ACTUATOR_DICT["spring"]

        for side in ("left", "right"):
            active = QPixmap(spring_desc["sprite_active_path"])
            inactive = QPixmap(spring_desc["sprite_inactive_path"])

            active = active.scaled(
                round(active.width() * SPRING_SCALE),
                round(active.height() * SPRING_SCALE),
                transformMode=Qt.TransformationMode.SmoothTransformation,
            )
            inactive = inactive.scaled(
                round(inactive.width() * SPRING_SCALE),
                round(inactive.height() * SPRING_SCALE),
                transformMode=Qt.TransformationMode.SmoothTransformation,
            )

            if side == "right":
                active = active.transformed(QTransform().scale(-1, 1))
                inactive = inactive.transformed(QTransform().scale(-1, 1))

            self.spring_visuals[side] = {"active": active, "inactive": inactive}

            w, h = active.width(), active.height()
            x = body.left() - w if side == "left" else body.right()
            y = body.top() - h / 3  # overlaps the body's top edge, in the chamber's upper corner

            self.spring_rects[side] = QRectF(x, y, w, h)

    def _spring_pixmap_for(self, side: str):
        visuals = self.spring_visuals.get(side)
        if not visuals:
            return None
        return visuals["active"] if self.bits.get(side, 0) else visuals["inactive"]

    def apply_properties(self):
        self.initialize_body_visuals()
        self.initialize_actuators()
        self.update_actuators_visuals()
        self.update()

    def extend_context_menu(self, menu: QMenu):
        super().extend_context_menu(menu)
        if self.simulation_mode:
            # Simulation running: actuators/default position mutate
            # self.properties -- unavailable while simulation_mode is
            # True (the hydraulic 4/2 valve gets "Simular defeito..." via
            # NodeItem.extend_context_menu, called above).
            return
        menu.addSeparator()

        left_menu = menu.addMenu(QCoreApplication.translate("DirectionalValveItem", "Left actuator"))
        right_menu = menu.addMenu(QCoreApplication.translate("DirectionalValveItem", "Right actuator"))

        self._populate_actuator_menu(left_menu, side="left")
        self._populate_actuator_menu(right_menu, side="right")

        menu.addSeparator()
        rest_menu = menu.addMenu(QCoreApplication.translate("DirectionalValveItem", "Default position"))
        if self.THREE_POSITION:
            rest_options = [
                ("right", QCoreApplication.translate("DirectionalValveItem", "Right (0)")),
                ("center", QCoreApplication.translate("DirectionalValveItem", "Center (1)")),
                ("left", QCoreApplication.translate("DirectionalValveItem", "Left (2)")),
            ]
            current_default = self.properties.get("default_side", "center")
        else:
            rest_options = [
                ("right", QCoreApplication.translate("DirectionalValveItem", "Right (0)")),
                ("left", QCoreApplication.translate("DirectionalValveItem", "Left (1)")),
            ]
            current_default = self.properties.get("default_side", "right")
        for opt, label in rest_options:
            action = QAction(label, menu, checkable=True)
            action.setChecked(current_default == opt)
            action.triggered.connect(lambda _, o=opt: self._set_default_side(o))
            rest_menu.addAction(action)

    def _populate_actuator_menu(self, menu: QMenu, side: str):
        current = self.actuators.get(side)

        # -----------------------
        # "None" option
        # -----------------------
        action_none = QAction(QCoreApplication.translate("DirectionalValveItem", "None"), menu, checkable=True)
        action_none.setChecked(current is None)
        action_none.triggered.connect(
            lambda _, s=side: self.set_actuator(s, None)
        )
        menu.addAction(action_none)
        menu.addSeparator()

        # -----------------------
        # ACTUATOR_DICT actuators
        # -----------------------
        for name, desc in ACTUATOR_DICT.items():
            if not desc.get("menu", True):
                continue
            if self.THREE_POSITION and name == "spring":
                continue
            if name == "button":
                self._add_button_actuator_menu(menu, side, desc, current)
                continue
            action = QAction(desc["label"], menu, checkable=True)
            action.setChecked(current is not None and current.get("type") == name)
            action.triggered.connect(
                lambda _, s=side, n=name: self.set_actuator(s, n)
            )
            menu.addAction(action)

        # -----------------------
        # Cylinder sensors (limit_switch)
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
            # Electric sensors (solenoid)
            # -----------------------
            electric_signals = self.sensor_registry.list_names(sensor_type="solenoid_coil")
            if electric_signals:
                menu.addSeparator()
                for sensor_name in electric_signals:
                    action = QAction(sensor_name, menu, checkable=True)
                    # marks it selected if this sensor is of type solenoid
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

    def _add_button_actuator_menu(self, menu: QMenu, side: str, desc: dict, current: dict | None):
        """"Button" gets a submenu instead of a flat action, so the user
        can pick latch (toggle) or momentary (active while held)."""
        button_menu = menu.addMenu(desc["label"])
        current_mode = current.get("mode", DEFAULT_BUTTON_MODE) if current and current.get("type") == "button" else None

        for mode, label in (
            ("latch", QCoreApplication.translate("DirectionalValveItem", "Latched")),
            ("momentary", QCoreApplication.translate("DirectionalValveItem", "Momentary")),
        ):
            action = QAction(label, button_menu, checkable=True)
            action.setChecked(current_mode == mode)
            action.triggered.connect(
                lambda _, s=side, m=mode: self.set_actuator(s, "button", mode=m)
            )
            button_menu.addAction(action)

    def _set_default_side(self, side: str):
        if self.properties.get("default_side") == side:
            return
        self.properties["default_side"] = side
        if not self.simulation_mode:
            if self.THREE_POSITION:
                self.body_state = THREE_POSITION_SIDE_MAP.get(side, 1)
            else:
                self.body_state = 1 if side == "left" else 0
            self.update_body_visuals()
            self.update_connections()
            self.update()

    def set_actuator(self, side: str, actuator_name: str | None, actuator_sensor_name: str | None = None, delay_steps: int | None = None, mode: str | None = None):
        current = self.properties["actuators"].get(side)

        if actuator_name is None:
            new_value = None
        elif actuator_name in ["limit_switch", "solenoid"]:
            new_value = {
                "type": actuator_name,
                "sensor_name": actuator_sensor_name,
            }
        elif actuator_name == "timer":
            new_value = {
                "type": "timer",
                "delay_steps": delay_steps if delay_steps is not None else 3,
            }
        elif actuator_name == "button":
            new_value = {
                "type": "button",
                "mode": mode or DEFAULT_BUTTON_MODE,
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

        # validates it exists in the registry
        if self.sensor_registry and not self.sensor_registry.exists(new_name):
            # reverts to the old one
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

    
    def build_properties_dialog(self):
        # QCoreApplication.translate(...) with an explicit
        # "DirectionalValveItem" context, not self.tr(...): this method is
        # inherited-and-called (never overridden) by every concrete valve
        # (Valve_2_2_Ways, Valve_3_2_Ways, ...), whose runtime class
        # self.tr() would resolve against instead -- same gotcha as
        # NodeItem.extend_context_menu (see Task 11's fix note in
        # main_window/actions/__init__.py). ACTUATOR_DICT's "label" values
        # are plain data (dict lookups aren't literal strings, so
        # pylupdate6 can't auto-extract them); their catalog entries are
        # added by hand.
        def _(text: str) -> str:
            return QCoreApplication.translate("DirectionalValveItem", text)

        dialog = PropertiesDialog(title=_("Directional Valve — Properties"))
        if self.domain == "hydraulic":
            dialog._field_k = dialog.add_number_field(
                # Reuses the same phrasing already cataloged for the
                # defect dialog's field of the same physical quantity.
                _("Conductance k (m³/s/√Pa)"), placeholder="ex: 1.5e-8",
                value=self.properties.get("k"),
                required=True,
            )
        else:
            dialog._field_k = None

        options = [(None, _("None"))]
        dialog._actuator_key_map = {}
        for key, desc in ACTUATOR_DICT.items():
            if not desc.get("menu", True):
                continue
            if self.THREE_POSITION and key == "spring":
                continue
            options.append((key, _(desc["label"])))
            dialog._actuator_key_map[key] = key

        if self.sensor_registry:
            for sensor_name in self.sensor_registry.list_names(sensor_type="cylinder_end"):
                options.append((sensor_name, sensor_name))
            for sensor_name in self.sensor_registry.list_names(sensor_type="solenoid_coil"):
                options.append((sensor_name, sensor_name))

        # determines the current selection (a canonical value: an
        # ACTUATOR_DICT key, a sensor name, or None -- never a translated
        # display label)
        def current_value(side):
            a = self.properties["actuators"].get(side)
            if not a:
                return None
            if a["type"] in ["limit_switch", "solenoid"]:
                return a.get("sensor_name")
            return a["type"]

        def _timer_delay(side):
            a = self.properties["actuators"].get(side)
            return a.get("delay_steps", 3) if a and a.get("type") == "timer" else 3

        def _button_is_latch(side):
            a = self.properties["actuators"].get(side)
            mode = a.get("mode", DEFAULT_BUTTON_MODE) if a and a.get("type") == "button" else DEFAULT_BUTTON_MODE
            return mode == "latch"

        # Helper to show/hide a row by widget reference
        def _set_row_visible(field, visible):
            form = dialog._form_layout
            for row in range(form.rowCount()):
                item = form.itemAt(row, form.ItemRole.FieldRole)
                if item and item.widget() is field:
                    form.setRowVisible(row, visible)
                    return

        # "Left actuator"/"Right actuator" reuse the phrasing already
        # cataloged for the context-menu submenu titles.
        dialog._combo_left = dialog.add_combo_field(_("Left actuator"), options, current=current_value("left"))
        dialog._field_timer_left = dialog.add_number_field(
            _("Timer delay — left (steps)"), placeholder="ex: 3",
            value=_timer_delay("left"), required=False,
        )
        dialog._field_latch_left = dialog.add_bool_field(
            _("Latch"), value=_button_is_latch("left"),
        )

        dialog._combo_right = dialog.add_combo_field(_("Right actuator"), options, current=current_value("right"))
        dialog._field_timer_right = dialog.add_number_field(
            _("Timer delay — right (steps)"), placeholder="ex: 3",
            value=_timer_delay("right"), required=False,
        )
        dialog._field_latch_right = dialog.add_bool_field(
            _("Latch"), value=_button_is_latch("right"),
        )

        if self.THREE_POSITION:
            default_side_options = [
                ("right", _("Right")), ("center", _("Center")), ("left", _("Left")),
            ]
            default_side_current = self.properties.get("default_side", "center")
        else:
            default_side_options = [("right", _("Right")), ("left", _("Left"))]
            default_side_current = self.properties.get("default_side", "right")
        dialog._combo_default_side = dialog.add_combo_field(
            _("Default position"),
            default_side_options,
            current=default_side_current,
        )

        # Show/hide timer delay / latch rows based on combo selection --
        # compares the canonical value (currentData()), not the
        # (translatable) displayed text.
        dialog._combo_left.currentIndexChanged.connect(
            lambda _i, combo=dialog._combo_left: (
                _set_row_visible(dialog._field_timer_left, combo.currentData() == "timer"),
                _set_row_visible(dialog._field_latch_left, combo.currentData() == "button"),
            )
        )
        dialog._combo_right.currentIndexChanged.connect(
            lambda _i, combo=dialog._combo_right: (
                _set_row_visible(dialog._field_timer_right, combo.currentData() == "timer"),
                _set_row_visible(dialog._field_latch_right, combo.currentData() == "button"),
            )
        )

        # Set initial visibility
        _set_row_visible(dialog._field_timer_left,  current_value("left")  == "timer")
        _set_row_visible(dialog._field_timer_right, current_value("right") == "timer")
        _set_row_visible(dialog._field_latch_left,  current_value("left")  == "button")
        _set_row_visible(dialog._field_latch_right, current_value("right") == "button")

        return dialog

    def apply_properties_from_dialog(self, dialog):
        if dialog._field_k is not None:
            k_text = dialog._field_k.text().strip()
            self.properties["k"] = float(k_text) if k_text else None
        for side, combo, timer_field, latch_field in [
            ("left",  dialog._combo_left,  dialog._field_timer_left,  dialog._field_latch_left),
            ("right", dialog._combo_right, dialog._field_timer_right, dialog._field_latch_right),
        ]:
            selected = combo.currentData()
            if selected is None:
                self.set_actuator(side, None)
            elif selected in dialog._actuator_key_map:
                key = dialog._actuator_key_map[selected]
                if key == "timer":
                    try:
                        delay = max(1, int(float(timer_field.text().strip() or "3")))
                    except ValueError:
                        delay = 3
                    self.set_actuator(side, "timer", delay_steps=delay)
                elif key == "button":
                    mode = "latch" if latch_field.isChecked() else "momentary"
                    self.set_actuator(side, "button", mode=mode)
                else:
                    self.set_actuator(side, key)
            elif self.sensor_registry:
                info = self.sensor_registry.get(selected)
                if info:
                    actuator_type = "limit_switch" if info.sensor_type == "cylinder_end" else "solenoid"
                    self.set_actuator(side, actuator_type, selected)

        self.properties["default_side"] = dialog._combo_default_side.currentData()
        side = self.properties["default_side"]
        if not self.simulation_mode:
            if self.THREE_POSITION:
                self.body_state = THREE_POSITION_SIDE_MAP.get(side, 1)
            else:
                self.body_state = 1 if side == "left" else 0
            self.update_body_visuals()
            self.update_connections()
            self.update()

    # -- Simulate defect (shared by all directional valves) ----------------
    # Promoted up here (instead of duplicated per subtype) because the 5
    # hydraulic directional valves (2/2, 3/2, 4/2, 4/3, 5/2) use exactly
    # the same protocol -- only k (conductance) and the "stuck" flag
    # change physical meaning between them, never the dialog/command
    # mechanics. Each subtype already exposes its name via
    # palette_meta(), reused here as the title.

    def build_defect_dialog(self):
        if self.domain != "hydraulic":
            return None

        domain_node = self._domain_node
        current_k = domain_node.k if domain_node is not None else self.properties.get("k")
        current_stuck = bool(getattr(domain_node, "_stuck_defect", False)) if domain_node is not None else False

        meta = type(self).palette_meta()
        # meta can be None (NodeItem.palette_meta()'s default for
        # abstract classes) and meta.name can be None (PaletteMeta
        # documents "uses cls.__name__" in that case, a convention
        # node_registry.py already follows) -- same fallback here, so
        # the context menu never breaks.
        label = (meta.name if meta else None) or type(self).__name__
        dialog = DefectDialog(
            title=QCoreApplication.translate(
                "DirectionalValveItem", "Simulate defect — {0}"
            ).format(label)
        )
        dialog._field_k = dialog.add_number_field(
            QCoreApplication.translate("DirectionalValveItem", "Conductance k (m³/s/√Pa)"),
            placeholder="ex: 1.5e-8",
            value=current_k, required=True, min_value=0,
        )
        dialog._field_stuck = dialog.add_bool_field(
            QCoreApplication.translate("DirectionalValveItem", "Valve stuck (won't switch)"),
            value=current_stuck,
        )
        return dialog

    def apply_defect_from_dialog(self, dialog):
        if dialog.restore_requested:
            self.command.emit(self.id, {"action": "clear_defect"})
            return

        k_text = dialog._field_k.text().strip()
        self.command.emit(self.id, {
            "action": "set_defect",
            "k": float(k_text),
            "stuck": dialog._field_stuck.isChecked(),
        })
