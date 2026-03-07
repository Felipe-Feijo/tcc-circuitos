from PyQt6.QtGui import QPixmap, QPainterPath, QAction
from PyQt6.QtCore import QRectF, QPointF, Qt
from PyQt6.QtWidgets import QMessageBox

from graphics.items.base.nodes.node_item import NodeItem
from graphics.labels.label import LabelItem
from graphics.utils.properties_dialog import PropertiesDialog
from .....anchors.anchor import AnchorItem

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
    Classe base para todos os pistões.
    A subclasse deve definir BODY_VISUALS.
    """

    BODY_VISUALS = {}  # definido pela subclasse

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.properties = {
            "sensors": {
                "retracted": {
                    "type": None,
                    "name": "",
                },
                "extended": {
                    "type": None,
                    "name": "",
                },
            }
        }

        self.sensors = {}
        self.sensor_rects = {}

        self.initialize_body_visuals()
        self.initialize_anchors()
        self.initialize_sensors()

    # --------------------------
    # Inicialização
    # --------------------------
    def initialize_body_visuals(self):
        self.body_visuals = {
            state: {
                "sprite": QPixmap(desc["sprite"]),
                "offset": desc.get("offset", QPointF(0, 0))
            }
            for state, desc in self.BODY_VISUALS.items()
        }

        # estado inicial
        self.body_state = min(self.body_visuals.keys())
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
    # Geometria
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
                # caso ainda tenha algum rect
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
    # Desenho
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
        painter.drawPixmap(
            int(self.visual_offset.x()),
            int(self.visual_offset.y()),
            self.body_sprite
        )

    # --------------------------
    # Atualização de estado
    # --------------------------
    def update_from_domain(self, domain_node):
        """
        Espera-se que o domain_node exponha
        um estado visual inteiro (ex: 0 ou 1).
        """
        super().update_from_domain(domain_node)
        new_state = domain_node.get_visual_state()

        if new_state == self.body_state:
            return

        self.body_state = new_state
        self.update_body_visuals()

        self.update_connections()
        self.update()

    def apply_properties(self):
        # remove qualquer registro antigo desse node
        for pos in ["retracted", "extended"]:
            self._unregister_sensor(pos)

        self.initialize_sensors()

        # registra sensores carregados
        for pos in ["retracted", "extended"]:
            sensor = self.properties["sensors"].get(pos)
            if sensor and sensor.get("type") is not None:
                self._register_sensor(pos)

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

        # Mapeia posição → índice do body_visuals
        pos_to_index = {"retracted": 0, "extended": 1}

        for pos in ["retracted", "extended"]:
            sensor = self.sensors.get(pos)
            label_name = f"sensor_{pos}"

            if sensor and sensor.get("type") is not None:
                visual = self.body_visuals[pos_to_index[pos]]
                sprite = visual["sprite"]
                offset = visual["offset"]

                # Cria o label editável
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

                # Cria a linha vertical abaixo do label
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

        # acessa a label correspondente
        label_name = f"sensor_{position}"
        label = self.special_labels.get(label_name)
        
        if not ok:
            # volta ao antigo nome
            sensor["name"] = old_name
            if label:
                label.set_text(old_name)  # atualiza visual
            QMessageBox.warning(None, "Erro ao renomear sensor",
                                f"Já existe um sensor com o nome '{new_name}'.")
            return

        # renomeação ok
        sensor["name"] = new_name
        if label:
            label.set_text(new_name)  # atualiza visual

    def extend_context_menu(self, menu):
        super().extend_context_menu(menu)
        menu.addSeparator()

        r_menu = menu.addMenu("Sensor retraído")
        e_menu = menu.addMenu("Sensor estendido")

        self._populate_sensor_menu(r_menu, "retracted")
        self._populate_sensor_menu(e_menu, "extended")

        

    def _populate_sensor_menu(self, menu, position):
        sensor = self.properties["sensors"][position]
        current = sensor.get("type")

        action_none = QAction("None", menu, checkable=True)
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

        # 🔻 se estava ativo, remove da registry
        if sensor["type"] is not None:
            self._unregister_sensor(position)

        sensor["type"] = sensor_type

        # 🔺 se passou a existir, registra
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


    def _unregister_sensor(self, position):
        sensor = self.properties["sensors"][position]
        name = sensor.get("name")

        if name:
            self.sensor_registry.unregister(name)

    def build_properties_dialog(self):
        dialog = PropertiesDialog(title="Cylinder — Properties")

        sensor_options = ["None"] + [desc["label"] for desc in SENSOR_DICT.values()]
        dialog._sensor_label_to_key = {desc["label"]: key for key, desc in SENSOR_DICT.items()}

        def make_side_widgets(pos):
            sensor = self.properties["sensors"].get(pos)
            current_type = sensor.get("type") if sensor else None
            current_label = SENSOR_DICT[current_type]["label"] if current_type else "None"
            current_name = sensor.get("name", "") if sensor else ""

            combo = dialog.add_combo_field(f"Sensor {pos}", sensor_options, current=current_label)
            name_field = dialog.add_text_field("  Nome", placeholder="ex: A1", value=current_name)
            name_field.setEnabled(current_type is not None)

            def on_type_changed(label):
                is_none = label == "None"
                name_field.setEnabled(not is_none)
                if not is_none and not name_field.text().strip():
                    name_field.setText(self.sensor_registry.next_available_name("A"))

            combo.currentTextChanged.connect(on_type_changed)
            return combo, name_field

        dialog._combo_retracted, dialog._name_retracted = make_side_widgets("retracted")
        dialog._combo_extended, dialog._name_extended = make_side_widgets("extended")

        return dialog

    def apply_properties_from_dialog(self, dialog):
        label_to_key = dialog._sensor_label_to_key

        for pos, combo, name_field in [
            ("retracted", dialog._combo_retracted, dialog._name_retracted),
            ("extended", dialog._combo_extended, dialog._name_extended),
        ]:
            label = combo.currentText()
            sensor_type = label_to_key.get(label) if label != "None" else None
            name = name_field.text().strip() if sensor_type else ""

            self.set_sensor(pos, sensor_type)
            if sensor_type and name:
                self._set_sensor_name(pos, name)