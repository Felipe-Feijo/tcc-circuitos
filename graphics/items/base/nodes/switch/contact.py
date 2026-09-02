"""Generic NO/NC electric contact graphics node.

Used to be split across a NodeItem subclass (SwitchItem) shared by two
sibling classes (ButtonSwitch and RelaySwitch). Both merged into this
single class -- the schematic symbol is identical whatever actuates the
contact (a direct click, a relay/solenoid coil, or a cylinder limit
switch), so "Button" is just another entry in the actuator list, with
its cap drawn as an overlay on top of the bare contact body instead of
a separate set of sprites. With only one concrete switch type left,
the SwitchItem split no longer earns its keep.
"""

from PyQt6.QtCore import QPointF, QRectF, Qt, QCoreApplication
from PyQt6.QtGui import QAction, QPainterPath, QPixmap
from PyQt6.QtWidgets import QMenu
from simulation.nodes.switch.contact import Contact as ContactNode

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.labels.label import LabelItem
from .....anchors.anchor import AnchorItem

# Sentinel for "actuator_sensor": the contact is driven by a direct click
# instead of a named coil/cylinder sensor. Not a real registered sensor
# name, so it's never looked up in the sensor registry.
BUTTON_SENSOR = "__button__"

DEFAULT_BUTTON_MODE = "momentary"  # active only while held; latch is opt-in

# Two behaviors, same overlay: "latch" toggles on click (default, matches
# today's behavior); "momentary" is active only while held (press = 1,
# release = 0). Same convention as the directional valve's button actuator.
BUTTON_OVERLAY_SPRITES = {
    "latch": {
        0: "resources/actuators/contact_button/contact_button_latch_inactive.png",
        1: "resources/actuators/contact_button/contact_button_latch_active.png",
    },
    "momentary": {
        0: "resources/actuators/contact_button/contact_button_inactive.png",
        1: "resources/actuators/contact_button/contact_button_active.png",
    },
}

# Where to draw the button overlay (relative to the body sprite's own
# corner, i.e. self.visual_offset) so the composited result reproduces
# the legacy button_switch_*.png sprites pixel-for-pixel. Found by
# exhaustive search over the old sprites -- don't hand-tune these without
# re-checking against tests/test_contact_button_actuator.py.
BUTTON_OVERLAY_OFFSETS = {
    ("NO", 0): QPointF(2, 25),
    ("NO", 1): QPointF(21, 25),
    ("NC", 0): QPointF(7, 25),
    ("NC", 1): QPointF(22, 25),
}


class Contact(NodeItem):
    node_type = "contact"
    simulation_cls = ContactNode
    SWITCH_VISUALS = {
        "NO": {
            0: {
                "sprite": "resources/nodes/contact/contact_no_open.png",
                "offset": QPointF(0, 0),
            },
            1: {
                "sprite": "resources/nodes/contact/contact_no_closed.png",
                "offset": QPointF(0, 0),
            },
        },
        "NC": {
            0: {
                "sprite": "resources/nodes/contact/contact_nc_closed.png",
                "offset": QPointF(0, 0),
            },
            1: {
                "sprite": "resources/nodes/contact/contact_nc_open.png",
                "offset": QPointF(0, 0),
            },
        }
    }

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("electric",),
            sprite=cls.SWITCH_VISUALS["NO"][0]["sprite"],
            name=QCoreApplication.translate("Contact", "Contact"),
        )

    # --------------------------
    # Setup
    # --------------------------

    def setup(self) -> None:
        self.properties = {"contact_type": "NO"}
        self.body_state = 0
        self.initialize_body_visuals()
        self.initialize_anchors()

        self.properties.setdefault("actuator_sensor", None)
        self.properties.setdefault("button_mode", DEFAULT_BUTTON_MODE)
        self._button_overlay_pixmaps = {
            mode: {state: QPixmap(path) for state, path in sprites.items()}
            for mode, sprites in BUTTON_OVERLAY_SPRITES.items()
        }
        self._momentary_pressed = False
        self._init_label()

    def register_sensors(self) -> None:
        if self.sensor_registry:
            self.sensor_registry.sensor_added.connect(self._on_sensor_registry_changed)
            self.sensor_registry.sensor_removed.connect(self._on_sensor_registry_changed)
            self.sensor_registry.sensor_renamed.connect(self._on_sensor_renamed)

    def initialize_anchors(self):
        self.add_anchor(AnchorItem("T", QPointF(self.width*39/50, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))
        self.add_anchor(AnchorItem("B", QPointF(self.width*39/50, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))

    # --------------------------
    # Body visuals
    # --------------------------

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

        # base dimensions
        self.width = self.body_sprite.width()
        self.height = self.body_sprite.height()

    def update_body_visuals(self):
        contact_type = self.properties["contact_type"]
        state = self.body_state

        visual = self.body_visuals[contact_type][state]

        self.body_sprite = visual["sprite"]
        self.visual_offset = visual["offset"]

    def update_from_domain(self, domain_node):
        super().update_from_domain(domain_node)
        self.body_state = domain_node.state
        self.update_body_visuals()
        self.update_connections()
        self.update()

    # --------------------------
    # Mouse / painting
    # --------------------------

    def mousePressEvent(self, event) -> None:
        """Toggle (latch) or activate (momentary, only while held) on
        click in simulation mode."""
        if self.simulation_mode and event.button() == Qt.MouseButton.LeftButton:
            if self._is_momentary_button():
                self._momentary_pressed = True
                self.command.emit(self.id, {"type": "switch", "value": 1})
            else:
                new_state = 0 if self.body_state else 1
                self.command.emit(self.id, {"type": "switch", "value": new_state})
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._momentary_pressed:
            self._momentary_pressed = False
            self.command.emit(self.id, {"type": "switch", "value": 0})
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _is_momentary_button(self) -> bool:
        return (
            self.properties.get("actuator_sensor") == BUTTON_SENSOR
            and self.properties.get("button_mode", DEFAULT_BUTTON_MODE) == "momentary"
        )

    def paint(self, painter, option, widget=None):
        self.draw_pixmap(painter, QPointF(int(self.visual_offset.x()), int(self.visual_offset.y())), self.body_sprite)
        self.paint_selection_feedback(painter)

        overlay = self._button_overlay()
        if overlay is None:
            return
        pixmap, offset = overlay
        pos = self.visual_offset + offset
        self.draw_pixmap(painter, QPointF(int(pos.x()), int(pos.y())), pixmap)

    def _button_overlay(self):
        """Returns (pixmap, offset) for the button-actuator overlay, or
        None when this contact isn't driven by "Button"."""
        if self.properties.get("actuator_sensor") != BUTTON_SENSOR:
            return None
        contact_type = self.properties.get("contact_type", "NO")
        offset = BUTTON_OVERLAY_OFFSETS.get((contact_type, self.body_state))
        if offset is None:
            return None
        mode = self.properties.get("button_mode", DEFAULT_BUTTON_MODE)
        pixmaps = self._button_overlay_pixmaps.get(mode, {})
        return pixmaps.get(self.body_state), offset

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

    # --------------------------
    # Actuator-sensor label
    # --------------------------

    def _init_label(self):
        self.remove_label("actuator_sensor_name")
        sensor_name = self.properties.get("actuator_sensor")

        label = LabelItem(
            properties={
                "text": self._label_text_for(sensor_name),
                "editable": False,
                "movable": False,
                "border": False,
                "max_length": 3
            }
        )

        # positions to the left and vertically centered
        x = -label.boundingRect().width() - 10
        y = self.height / 2 - label.boundingRect().height() / 2
        label.setPos(QPointF(x, y))

        self.add_label("actuator_sensor_name", label)

    @staticmethod
    def _label_text_for(sensor_name: str | None) -> str:
        # "Button" isn't a named sensor -- nothing to display next to it.
        if sensor_name == BUTTON_SENSOR:
            return ""
        return sensor_name or ""

    # --------------------------
    # Contact type / actuator menu
    # --------------------------

    def _available_actuator_signals(self) -> list[str]:
        if not self.sensor_registry:
            return []
        return (
            self.sensor_registry.list_names(sensor_type="relay_coil")
            + self.sensor_registry.list_names(sensor_type="solenoid_coil")
            + self.sensor_registry.list_names(sensor_type="cylinder_end")
        )

    def build_properties_dialog(self):
        from graphics.utils.properties_dialog import PropertiesDialog
        dialog = PropertiesDialog(title="Contact — Properties")

        current_type = self.properties.get("contact_type", "NO")
        dialog._combo_contact = dialog.add_combo_field(
            "Tipo de contato",
            # "NO"/"NC" (Normally Open/Closed) are kept as-is in both
            # languages -- an internationally recognized electrical
            # abbreviation, not natural-language text.
            [("NO", "NO"), ("NC", "NC")],
            current=current_type,
        )

        actuator_signals = self._available_actuator_signals()

        current_sensor = self.properties.get("actuator_sensor")
        options = [(None, self.tr("(None)")), (BUTTON_SENSOR, self.tr("Button"))]
        options += [(name, name) for name in actuator_signals]
        if current_sensor == BUTTON_SENSOR:
            current_option = BUTTON_SENSOR
        elif current_sensor in actuator_signals:
            current_option = current_sensor
        else:
            current_option = None
        dialog._combo_relay = dialog.add_combo_field(
            "Atuador", options, current=current_option
        )

        current_mode = self.properties.get("button_mode", DEFAULT_BUTTON_MODE)
        dialog._field_latch = dialog.add_bool_field(
            "Trava", value=current_mode == "latch",
        )

        def _set_latch_visible(visible):
            form = dialog._form_layout
            for row in range(form.rowCount()):
                item = form.itemAt(row, form.ItemRole.FieldRole)
                if item and item.widget() is dialog._field_latch:
                    form.setRowVisible(row, visible)
                    return

        dialog._combo_relay.currentIndexChanged.connect(
            lambda _i, combo=dialog._combo_relay: _set_latch_visible(combo.currentData() == BUTTON_SENSOR)
        )
        _set_latch_visible(current_option == BUTTON_SENSOR)

        return dialog

    def apply_properties_from_dialog(self, dialog):
        self.set_contact_type(dialog._combo_contact.currentData())
        selected = dialog._combo_relay.currentData()
        if selected is None:
            self.set_actuator_sensor(None)
        elif selected == BUTTON_SENSOR:
            mode = "latch" if dialog._field_latch.isChecked() else "momentary"
            self.set_button_actuator(mode)
        else:
            self.set_actuator_sensor(selected)

    def extend_context_menu(self, menu: QMenu):
        if self.simulation_mode:
            # Simulation running: contact type / actuator selection mutate
            # self.properties -- unavailable while simulation_mode is True.
            super().extend_context_menu(menu)
            return

        menu.addSeparator()

        contact_menu = menu.addMenu(self.tr("Contact type"))
        for t in ("NO", "NC"):
            action = QAction(t, menu, checkable=True)
            action.setChecked(self.properties.get("contact_type") == t)
            action.triggered.connect(lambda _, x=t: self.set_contact_type(x))
            contact_menu.addAction(action)

        super().extend_context_menu(menu)

        menu.addSeparator()
        self._add_button_actuator_menu(menu)

        actuator_signals = self._available_actuator_signals()
        for sensor_name in actuator_signals:
            action = QAction(sensor_name, menu, checkable=True)

            is_checked = (
                getattr(self, "current_relay", None) == sensor_name
            )
            action.setChecked(is_checked)

            action.triggered.connect(
                lambda _, n=sensor_name: self.set_actuator_sensor(n)
            )
            menu.addAction(action)

    def _add_button_actuator_menu(self, menu: QMenu):
        """"Button" gets a submenu instead of a flat action, so the user
        can pick latch (toggle) or momentary (active while held)."""
        button_menu = menu.addMenu(self.tr("Button"))
        current_mode = (
            self.properties.get("button_mode", DEFAULT_BUTTON_MODE)
            if self.properties.get("actuator_sensor") == BUTTON_SENSOR
            else None
        )

        for mode, label in (("latch", self.tr("Latched")), ("momentary", self.tr("Momentary"))):
            action = QAction(label, button_menu, checkable=True)
            action.setChecked(current_mode == mode)
            action.triggered.connect(lambda _, m=mode: self.set_button_actuator(m))
            button_menu.addAction(action)

    def set_contact_type(self, contact_type: str):
        if self.properties.get("contact_type") == contact_type:
            return

        self.properties["contact_type"] = contact_type

        # updates the local visual immediately
        self.update_body_visuals()
        self.update_connections()
        self.update()

    def set_actuator_sensor(self, sensor_name: str | None):
        old_sensor = self.properties.get("actuator_sensor")
        if old_sensor == sensor_name:
            return

        self.properties["actuator_sensor"] = sensor_name

        # updates the label
        label = self.labels.get("actuator_sensor_name")
        if label:
            label.set_text(self._label_text_for(sensor_name))

        self.update()

    def set_button_mode(self, mode: str):
        if self.properties.get("button_mode", DEFAULT_BUTTON_MODE) == mode:
            return
        self.properties["button_mode"] = mode
        self.update()

    def set_button_actuator(self, mode: str):
        """Selects "Button" as the actuator with the given latch/momentary
        mode in one step -- used by the context menu submenu."""
        self.set_actuator_sensor(BUTTON_SENSOR)
        self.set_button_mode(mode)

    def apply_properties(self):
        """
        Updates the contact with the properties values.
        Especially used when loading/instantiating.
        """
        self._init_label()
        self.update()

    # --------------------------
    # Updates the manually selected sensor
    # --------------------------
    def _set_actuator_sensor_name(self, new_name: str):
        old_name = self.properties.get("actuator_sensor")
        if not new_name or new_name == old_name:
            return

        # validates it exists in the registry
        if self.sensor_registry and not self.sensor_registry.exists(new_name):
            # reverts to the old one
            label = self.labels.get("actuator_sensor_name")
            if label:
                label.set_text(old_name or "")
            return

        self.properties["actuator_sensor"] = new_name
        label = self.labels.get("actuator_sensor_name")
        if label:
            label.set_text(new_name)

    # --------------------------
    # Handling for when sensors are removed from the registry
    # --------------------------
    def _on_sensor_registry_changed(self, *args):
        changed = False
        current_sensor = self.properties.get("actuator_sensor")
        if (
            current_sensor
            and current_sensor != BUTTON_SENSOR
            and self.sensor_registry
            and not self.sensor_registry.exists(current_sensor)
        ):
            # sensor disappeared -> unlinks
            self.properties["actuator_sensor"] = None
            changed = True

        if changed:
            self._init_label()
            self.update()

    # --------------------------
    # Handling for sensor renaming
    # --------------------------
    def _on_sensor_renamed(self, old_name, new_name, node):
        current_sensor = self.properties.get("actuator_sensor")
        if current_sensor == old_name:
            self.properties["actuator_sensor"] = new_name
            label = self.labels.get("actuator_sensor_name")
            if label:
                label.set_text(new_name)
            self.update()
