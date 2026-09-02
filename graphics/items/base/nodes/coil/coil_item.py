"""Base class for electric coils (relay and solenoid)."""

from PyQt6.QtGui import QPixmap, QPainterPath
from PyQt6.QtCore import QPointF, QRectF, Qt, QCoreApplication
from PyQt6.QtWidgets import QMessageBox

from graphics.items.base.nodes.node_item import NodeItem
from graphics.labels.label import LabelItem
from .....anchors.anchor import AnchorItem


class CoilItem(NodeItem):
    """
    Base class for coils, parameterizable by sprite, prefix and signal type.
    """
    def setup(self) -> None:
        self.properties = {
            "sensor": {"coil": {"name": ""}}
        }
        self.sensors = self.properties["sensor"]
        self.energized: int = 0
        self.initialize_body_visuals()
        self.initialize_anchors()
        self.initialize_label()

    def register_sensors(self) -> None:
        if self.sensor_registry:
            self._register_sensor()

    def unregister_sensors(self) -> None:
        self._unregister_sensor()

    # --------------------------
    # Initialization
    # --------------------------

    def initialize_body_visuals(self):
        if not self.SPRITE_PATH:
            raise ValueError("SPRITE_PATH must be defined in the subclass")

        self.body_sprite = QPixmap(self.SPRITE_PATH)
        self.visual_offset = QPointF(0, 0)
        self.width = self.body_sprite.width()
        self.height = self.body_sprite.height()

    def initialize_anchors(self):
        """
        Two electric anchors:
        - top
        - bottom
        both centered on the width
        """
        x = self.width / 2
        self.add_anchor(AnchorItem("T", QPointF(x, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))
        self.add_anchor(AnchorItem("B", QPointF(x, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))

    def initialize_label(self):
        """
        Editable label to the left of the sprite, vertically centered.
        """
        label = LabelItem(
            properties={
                "text": self.properties["sensor"].get("name", ""),
                "editable": True,
                "movable": False,
                "max_length": 3,
                "on_commit": self._set_sensor_name,
                "border": False,
            }
        )

        x = -label.boundingRect().width() - 25
        y = self.height / 2 - label.boundingRect().height() / 2
        label.setPos(QPointF(x, y))
        self.add_label("sensor_name", label, special=True)

    # --------------------------
    # Geometry
    # --------------------------

    def boundingRect(self):
        margin = 10
        return QRectF(
            -50,
            -margin,
            self.width + 50 + margin,
            self.height + 2 * margin
        )

    def shape(self):
        path = QPainterPath()
        path.addRect(QRectF(0, 0, self.width, self.height))
        return path

    # --------------------------
    # Drawing
    # --------------------------


    def build_properties_dialog(self):
        from graphics.utils.properties_dialog import PropertiesDialog
        # QCoreApplication.translate(...) with an explicit "CoilItem"
        # context, not self.tr(...): this method is inherited-and-called
        # (never overridden) by RelayCoil/SolenoidCoil, whose runtime
        # class self.tr() would resolve against instead -- same gotcha as
        # NodeItem.extend_context_menu (see Task 11's fix note in
        # main_window/actions/__init__.py).
        dialog = PropertiesDialog(title=QCoreApplication.translate("CoilItem", "Coil — Properties"))
        current_name = self.properties["sensor"]["coil"].get("name", "")
        dialog._name_field = dialog.add_text_field(
            QCoreApplication.translate("CoilItem", "Sensor name"),
            placeholder=f"ex: {self.PREFIX}1",
            value=current_name,
        )
        return dialog

    def apply_properties_from_dialog(self, dialog):
        new_name = dialog._name_field.text().strip()
        if new_name:
            self._set_sensor_name(new_name)

    def update_from_domain(self, domain_node) -> None:
        """Update visual from domain Coil state (called each sim step)."""
        super().update_from_domain(domain_node)
        self.energized = getattr(domain_node, "energized", 0)
        self.update()

    def on_simulation_activated(self) -> None:
        self.energized = 0
        self.update()

    def reset_visual_state(self) -> None:
        self.energized = 0
        super().reset_visual_state()

    def paint(self, painter, option, widget=None):
        self.draw_pixmap(painter, QPointF(int(self.visual_offset.x()), int(self.visual_offset.y())), self.body_sprite)
        self.paint_selection_feedback(painter)

    # --------------------------
    # Registry
    # --------------------------

    def _register_sensor(self):
        sensor = self.sensors["coil"]
        name = sensor.get("name")

        if not name:
            name = self.sensor_registry.next_available_name(self.PREFIX)
            sensor["name"] = name

        self.sensor_registry.register(
            name=name,
            sensor_type=self.SENSOR_TYPE,
            node=self
        )

        label = self.special_labels.get("sensor_name")
        if label:
            label.set_text(name)

    def _unregister_sensor(self):
        sensor = self.sensors.get("coil")
        sensor_name = sensor.get("name") if sensor else None

        if self.sensor_registry:
            if sensor_name and self.sensor_registry.exists(sensor_name):
                self.sensor_registry.unregister(sensor_name)
            else:
                label = self.special_labels.get("sensor_name")
                if label:
                    label_name = label.toPlainText()
                    if label_name and self.sensor_registry.exists(label_name):
                        self.sensor_registry.unregister(label_name)

        # clears the label (the dict is NOT reset here: apply_properties()
        # calls _unregister_sensor() right after rebinding self.sensors to
        # the freshly loaded properties, and the name there is already
        # the value _register_sensor() should register next -- clearing
        # it would erase that value before it's read).
        label = self.special_labels.get("sensor_name")
        if label:
            label.set_text("")

    def _set_sensor_name(self, new_name):
        sensor = self.sensors["coil"]  # -- 'coil' key
        old_name = sensor.get("name")

        if not new_name or new_name == old_name:
            return

        ok = self.sensor_registry.rename(old_name, new_name, self)
        label = self.special_labels.get("sensor_name")

        if not ok:
            if label:
                label.set_text(old_name)  # reverts to the old name
            QMessageBox.warning(
                None,
                QCoreApplication.translate("CoilItem", "Error renaming"),
                QCoreApplication.translate(
                    "CoilItem", "A signal named '{0}' already exists."
                ).format(new_name),
            )
            return

        sensor["name"] = new_name
        if label:
            label.set_text(new_name)

    def apply_properties(self):
        self.sensors = self.properties["sensor"]
        self._unregister_sensor()
        label = self.special_labels.get("sensor_name")
        if label:
            label.set_text(self.properties["sensor"]["coil"].get("name", ""))
        self._register_sensor()
        self.update()