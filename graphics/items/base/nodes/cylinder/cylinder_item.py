"""Base class for pneumatic and hydraulic cylinders."""

from PyQt6.QtGui import QPixmap, QPainterPath, QAction
from PyQt6.QtCore import QRectF, QPointF, Qt, QCoreApplication
from PyQt6.QtWidgets import QMessageBox

from graphics.items.base.nodes.node_item import NodeItem
from graphics.labels.label import LabelItem
from graphics.utils.properties_dialog import PropertiesDialog

SENSOR_DICT = {
    "reed": {
        "label": "Reed switch",
    },
    "proximity": {
        "label": "Proximity",
    },
}
class CylinderItem(NodeItem):
    """
    Base class for all pistons.
    The subclass must define BODY_VISUALS.
    """

    BODY_VISUALS = {}  # defined by the subclass

    def setup(self) -> None:
        self.properties = {
            "sensors": {
                "retracted": {"type": None, "name": ""},
                "extended":  {"type": None, "name": ""},
            },
            "default_state": "retracted",  # "retracted" = 0, "extended" = 1
        }
        self.sensors = {}
        self.sensor_rects = {}
        self.initialize_body_visuals()
        self.initialize_anchors()
        self.initialize_sensors()
        if self.domain == "hydraulic":
            self._init_velocity_label()

    def register_sensors(self) -> None:
        for pos in ("retracted", "extended"):
            sensor = self.properties["sensors"].get(pos)
            if sensor and sensor.get("type") is not None:
                self._register_sensor(pos)

    # --------------------------
    # Initialization
    # --------------------------
    def initialize_body_visuals(self):
        self.body_visuals = {
            state: {
                "sprite": QPixmap(desc["sprite"]),
                "offset": desc.get("offset", QPointF(0, 0))
            }
            for state, desc in self.BODY_VISUALS.items()
        }

        # initial state respecting default_state
        default = self.properties.get("default_state", "retracted")
        self.body_state = 1 if default == "extended" else 0
        visual = self.body_visuals[self.body_state]

        self.body_sprite = visual["sprite"]
        self.visual_offset = visual["offset"]

        self.width = self.body_sprite.width()
        self.height = self.body_sprite.height()

        self._compute_max_bounding_rect()

    def _compute_max_bounding_rect(self):
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")

        for visual in self.body_visuals.values():
            sprite = visual["sprite"]
            offset = visual["offset"]

            x0 = offset.x()
            y0 = offset.y()
            x1 = x0 + sprite.width()
            y1 = y0 + sprite.height()

            min_x = min(min_x, x0)
            min_y = min(min_y, y0)
            max_x = max(max_x, x1)
            max_y = max(max_y, y1)

        self._max_body_rect = QRectF(
            min_x,
            min_y,
            max_x - min_x,
            max_y - min_y
        )

    def initialize_anchors(self):
        pass

    # --------------------------
    # Geometry
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
        return self._max_body_rect.adjusted(
            -margin, -margin, margin, margin
        )

    def shape(self):
        path = QPainterPath()
        path.addRect(self.body_rect)

        for value in self.sensor_rects.values():
            if isinstance(value, QRectF):
                # in case there's still a rect
                path.addRect(value.translated(self.visual_offset))
            else:
                # assume tuple (x1, y1, x2, y2)
                x1, y1, x2, y2 = value
                dx = self.visual_offset.x()
                dy = self.visual_offset.y()
                path.moveTo(x1 + dx, y1 + dy)
                path.lineTo(x2 + dx, y2 + dy)

        return path

    # --------------------------
    # Drawing
    # --------------------------
    def paint(self, painter, option, widget=None):
        self.paint_body(painter)

        painter.setBrush(Qt.GlobalColor.white)
        painter.setPen(Qt.GlobalColor.white)

        for key, value in self.sensor_rects.items():
            # assume tuple (x1, y1, x2, y2)
            x1, y1, x2, y2 = value
            painter.drawLine(
                int(x1 + self.visual_offset.x()),
                int(y1 + self.visual_offset.y()),
                int(x2 + self.visual_offset.x()),
                int(y2 + self.visual_offset.y())
            )

        self.paint_selection_feedback(painter)


    def paint_body(self, painter):
        self.draw_pixmap(painter, QPointF(int(self.visual_offset.x()), int(self.visual_offset.y()),), self.body_sprite)

    # --------------------------
    # Velocity label (hydraulic)
    # --------------------------
    def _init_velocity_label(self):
        self._label_velocity = LabelItem(properties={
            "text": "v: 0 m/s",
            "editable": False,
            "movable": True,
            "border": False,
            "font_delta": -1,
        })
        self._label_velocity.setParentItem(self)
        # Positions above the center of the body
        cx = self.width / 2
        self._label_velocity.setPos(QPointF(cx, -18))

    def update_velocity_label(self, velocity: float):
        if not hasattr(self, "_label_velocity"):
            return
        if isinstance(velocity, str):
            self._label_velocity.set_text("v: ERR")
            return
        # Reuses the same formatter as the hydraulic anchors
        from graphics.anchors.anchor import AnchorItem
        v_str = AnchorItem.format_hydraulic_value(None, abs(velocity), "m/s")
        sign = "-" if velocity < -1e-10 else ""
        self._label_velocity.set_text(f"v: {sign}{v_str}")

    # --------------------------
    # State update
    # --------------------------
    def update_from_domain(self, domain_node):
        """
        The domain_node is expected to expose
        an integer visual state (e.g. 0 or 1).
        """
        super().update_from_domain(domain_node)
        new_state = domain_node.get_visual_state()

        if self.domain == "hydraulic":
            self._update_velocity_from_domain(domain_node)

        if new_state == self.body_state:
            return

        self.body_state = new_state
        self.update_body_visuals()

        self.update_connections()
        self.update()

    def _update_velocity_from_domain(self, domain_node):
        """Computes piston velocity from the domain node's flow and area."""
        try:
            anchor = domain_node.anchors.get("A")
            if anchor is None or isinstance(getattr(anchor, "flow", None), str):
                return

            flow = anchor.flow  # m^3/s

            # single acting uses `area`, double acting uses `area_a`
            area = getattr(domain_node, "area", None) or getattr(domain_node, "area_a", None)
            if not area:
                return

            velocity = flow / area  # m/s
            if abs(velocity) < 1e-8:
                velocity = 0.0
                
            self.update_velocity_label(velocity)
        except Exception:
            pass

    def reset_visual_state(self) -> None:
        super().reset_visual_state()
        if hasattr(self, "_label_velocity"):
            self._label_velocity.set_text("v: 0 m/s")

    def apply_properties(self) -> None:
        self.initialize_body_visuals()
        for pos in ("retracted", "extended"):
            self._unregister_sensor(pos)
        self.initialize_sensors()
        self.register_sensors()
        self.update()

    def update_body_visuals(self):
        visual = self.body_visuals.get(self.body_state)
        if not visual:
            return

        self.body_sprite = visual["sprite"]
        self.visual_offset = visual["offset"]

    def initialize_sensors(self):
        self.sensor_rects.clear()
        self.sensors = self.properties["sensors"]

        size = 8
        margin = 4
        line_length = 20

        # Maps position -> body_visuals index
        pos_to_index = {"retracted": 0, "extended": 1}

        for pos in ["retracted", "extended"]:
            sensor = self.sensors.get(pos)
            label_name = f"sensor_{pos}"

            if sensor and sensor.get("type") is not None:
                visual = self.body_visuals[pos_to_index[pos]]
                sprite = visual["sprite"]
                offset = visual["offset"]

                # Creates the editable label
                label = LabelItem(
                    properties={
                        "text": sensor.get("name", ""),
                        "editable": True,
                        "movable": False,
                        "max_length": 3,
                        "on_commit": lambda t, p=pos: self._set_sensor_name(p, t),
                        "border": True,
                    }
                )

                label_x = offset.x() + sprite.width() - size - margin
                label_y = offset.y()
                label.setPos(label_x, label_y)
                self.add_label(label_name, label, special=True)

                # Creates the vertical line below the label
                line_x = label_x + label.boundingRect().width() / 2
                line_y1 = label_y + label.boundingRect().height()
                line_y2 = line_y1 + line_length
                self.sensor_rects[pos] = (line_x, line_y1, line_x, line_y2)

            else:
                self.remove_label(label_name, special=True)


    def _set_sensor_name(self, position, new_name):
        sensor = self.properties["sensors"][position]
        old_name = sensor.get("name")

        if not new_name or new_name == old_name:
            return

        ok = self.sensor_registry.rename(old_name, new_name, self)

        # accesses the corresponding label
        label_name = f"sensor_{position}"
        label = self.special_labels.get(label_name)
        
        if not ok:
            # reverts to the old name
            sensor["name"] = old_name
            if label:
                label.set_text(old_name)  # updates the visual
            QMessageBox.warning(
                None,
                QCoreApplication.translate("CylinderItem", "Error renaming sensor"),
                QCoreApplication.translate(
                    "CylinderItem", "A sensor named '{0}' already exists."
                ).format(new_name),
            )
            return

        # rename ok
        sensor["name"] = new_name
        if label:
            label.set_text(new_name)  # updates the visual

    def extend_context_menu(self, menu):
        super().extend_context_menu(menu)
        if self.simulation_mode:
            # Simulation running: sensors/initial state mutate self.properties
            # -- unavailable while simulation_mode is True.
            return
        menu.addSeparator()

        r_menu = menu.addMenu(QCoreApplication.translate("CylinderItem", "Retracted sensor"))
        e_menu = menu.addMenu(QCoreApplication.translate("CylinderItem", "Extended sensor"))

        self._populate_sensor_menu(r_menu, "retracted")
        self._populate_sensor_menu(e_menu, "extended")

        menu.addSeparator()
        state_menu = menu.addMenu(QCoreApplication.translate("CylinderItem", "Initial state"))
        for opt, label in [
            ("retracted", QCoreApplication.translate("CylinderItem", "Retracted")),
            ("extended", QCoreApplication.translate("CylinderItem", "Extended")),
        ]:
            action = QAction(label, menu, checkable=True)
            action.setChecked(self.properties.get("default_state", "retracted") == opt)
            action.triggered.connect(lambda _, o=opt: self._set_default_state(o))
            state_menu.addAction(action)

    def _set_default_state(self, state: str):
        if self.properties.get("default_state") == state:
            return
        self.properties["default_state"] = state
        if not self.simulation_mode:
            self.body_state = 1 if state == "extended" else 0
            self.update_body_visuals()
            self.update_connections()
            self.update()

        

    def _populate_sensor_menu(self, menu, position):
        sensor = self.properties["sensors"][position]
        current = sensor.get("type")

        action_none = QAction(QCoreApplication.translate("CylinderItem", "None"), menu, checkable=True)
        action_none.setChecked(current is None)
        action_none.triggered.connect(
            lambda _, p=position: self.set_sensor(p, None)
        )
        menu.addAction(action_none)

        menu.addSeparator()

        for name, desc in SENSOR_DICT.items():
            action = QAction(desc["label"], menu, checkable=True)
            action.setChecked(current == name)
            action.triggered.connect(
                lambda _, p=position, n=name: self.set_sensor(p, n)
            )
            menu.addAction(action)

    def set_sensor(self, position, sensor_type):
        sensor = self.properties["sensors"][position]

        if sensor["type"] == sensor_type:
            return

        # if it was active, unregisters it
        if sensor["type"] is not None:
            self._unregister_sensor(position)

        sensor["type"] = sensor_type

        # if it now exists, registers it
        if sensor_type is not None:
            self._register_sensor(position)
        else:
            sensor["name"] = ""

        self.prepareGeometryChange()
        self.initialize_sensors()
        self.update()

    def _register_sensor(self, position):
        sensor = self.properties["sensors"][position]
        name = sensor.get("name")

        if not name:
            name = self.sensor_registry.next_available_name("A")
            sensor["name"] = name

        self.sensor_registry.register(
            name=name,
            sensor_type="cylinder_end",
            node=self
        )

        # Sync label text — may have been created before name was assigned
        label = self.special_labels.get(f"sensor_{position}")
        if label:
            label.set_text(name)


    def _unregister_sensor(self, position):
        sensor = self.properties["sensors"][position]
        name = sensor.get("name")

        if name:
            self.sensor_registry.unregister(name)

    def build_properties_dialog(self):
        dialog = PropertiesDialog(title="Cylinder — Properties")

        # QCoreApplication.translate(...) with an explicit "CylinderItem"
        # context, not self.tr(...): this method is inherited-and-called
        # via super() by DoubleActingCylinder/SingleActingCylinder, whose
        # runtime class self.tr() would resolve against instead -- same
        # gotcha as NodeItem.extend_context_menu (see Task 11's fix note
        # in main_window/actions/__init__.py). SENSOR_DICT's "label"
        # values are plain data (dict lookups aren't literal strings, so
        # pylupdate6 can't auto-extract them); their catalog entries are
        # added by hand, same treatment as ACTUATOR_DICT's labels in
        # directional_valve_item.py.
        def _(text: str) -> str:
            return QCoreApplication.translate("CylinderItem", text)

        sensor_options = [(None, _("None"))] + [
            (key, _(desc["label"])) for key, desc in SENSOR_DICT.items()
        ]

        # Tracks names already assigned within this dialog session so that
        # auto-generated names for multiple sensors don't collide.
        pending_names: set[str] = set()

        def next_name() -> str:
            """Next available name, skipping names already pending in dialog."""
            i = 1
            while True:
                candidate = f"A{i}"
                if not self.sensor_registry.exists(candidate) and candidate not in pending_names:
                    return candidate
                i += 1

        def make_side_widgets(pos):
            sensor = self.properties["sensors"].get(pos)
            current_type = sensor.get("type") if sensor else None
            current_name = sensor.get("name", "") if sensor else ""

            combo = dialog.add_combo_field(f"Sensor {pos}", sensor_options, current=current_type)
            name_field = dialog.add_text_field("  Nome", placeholder="ex: A1", value=current_name)
            name_field.setEnabled(current_type is not None)

            def on_type_changed(_index, combo=combo):
                sensor_type = combo.currentData()
                is_none = sensor_type is None
                name_field.setEnabled(not is_none)
                if not is_none and not name_field.text().strip():
                    name = next_name()
                    pending_names.add(name)
                    name_field.setText(name)

            def on_name_changed(text):
                # Keep pending_names in sync as user types
                pending_names.discard(name_field.property("_last_pending"))
                pending_names.add(text)
                name_field.setProperty("_last_pending", text)

            combo.currentIndexChanged.connect(on_type_changed)
            name_field.textChanged.connect(on_name_changed)
            return combo, name_field

        dialog._combo_retracted, dialog._name_retracted = make_side_widgets("retracted")
        dialog._combo_extended, dialog._name_extended = make_side_widgets("extended")

        dialog._combo_default_state = dialog.add_combo_field(
            "Estado inicial",
            [("retracted", _("Retracted")), ("extended", _("Extended"))],
            current=self.properties.get("default_state", "retracted"),
        )

        return dialog

    def apply_properties_from_dialog(self, dialog):
        for pos, combo, name_field in [
            ("retracted", dialog._combo_retracted, dialog._name_retracted),
            ("extended", dialog._combo_extended, dialog._name_extended),
        ]:
            sensor_type = combo.currentData()
            name = name_field.text().strip() if sensor_type else ""

            self.set_sensor(pos, sensor_type)
            if sensor_type and name:
                self._set_sensor_name(pos, name)

        self.properties["default_state"] = dialog._combo_default_state.currentData()
        self.apply_properties()