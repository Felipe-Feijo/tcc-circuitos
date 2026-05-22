"""Classe base para bobinas elétricas (relé e solenóide)."""

from PyQt6.QtGui import QPixmap, QPainterPath
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtWidgets import QMessageBox

from graphics.items.base.nodes.node_item import NodeItem
from graphics.labels.label import LabelItem
from .....anchors.anchor import AnchorItem


class CoilItem(NodeItem):
    """
    Classe base para bobinas, parametrizável para sprite, prefixo e tipo de sinal.
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
    # Inicialização
    # --------------------------

    def initialize_body_visuals(self):
        if not self.SPRITE_PATH:
            raise ValueError("SPRITE_PATH deve ser definido na subclasse")

        self.body_sprite = QPixmap(self.SPRITE_PATH)
        self.visual_offset = QPointF(0, 0)
        self.width = self.body_sprite.width()
        self.height = self.body_sprite.height()

    def initialize_anchors(self):
        """
        Duas anchors elétricas:
        - topo
        - fundo
        ambas centralizadas na largura
        """
        x = self.width / 2
        self.add_anchor(AnchorItem("T", QPointF(x, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))
        self.add_anchor(AnchorItem("B", QPointF(x, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))

    def initialize_label(self):
        """
        Label editável à esquerda do sprite, centrada verticalmente.
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
    # Geometria
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
    # Desenho
    # --------------------------


    def build_properties_dialog(self):
        from graphics.utils.properties_dialog import PropertiesDialog
        dialog = PropertiesDialog(title="Coil — Properties")
        current_name = self.properties["sensor"]["coil"].get("name", "")
        dialog._name_field = dialog.add_text_field(
            "Nome do sensor",
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

        # limpa label e o dict
        if sensor:
            sensor["name"] = ""
        label = self.special_labels.get("sensor_name")
        if label:
            label.set_text("")

    def _set_sensor_name(self, new_name):
        sensor = self.sensors["coil"]  # ← chave 'coil'
        old_name = sensor.get("name")

        if not new_name or new_name == old_name:
            return

        ok = self.sensor_registry.rename(old_name, new_name, self)
        label = self.special_labels.get("sensor_name")

        if not ok:
            if label:
                label.set_text(old_name)  # volta ao antigo nome
            QMessageBox.warning(None, "Erro ao renomear",
                                f"Já existe um sinal com o nome '{new_name}'.")
            return

        sensor["name"] = new_name
        if label:
            label.set_text(new_name)

    def apply_properties(self):
        self._unregister_sensor()
        label = self.special_labels.get("sensor_name")
        if label:
            label.set_text(self.properties["sensor"].get("name", ""))
        self._register_sensor()
        self.update()