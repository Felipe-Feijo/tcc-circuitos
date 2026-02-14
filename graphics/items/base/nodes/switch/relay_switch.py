from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu

from graphics.items.base.nodes.switch.switch_item import SwitchItem
from graphics.labels.label import LabelItem
from .....anchors.anchor import AnchorItem


class RelaySwitch(SwitchItem):
    SWITCH_VISUALS = {
        "NO": {
            0: {
                "sprite": "resources/nodes/relay_switch/relay_switch_no_open.png",
                "offset": QPointF(0, 0),
            },
            1: {
                "sprite": "resources/nodes/relay_switch/relay_switch_no_closed.png",
                "offset": QPointF(0, 0),
            },
        },
        "NC": {
            0: {
                "sprite": "resources/nodes/button_switch/button_switch_closed.png",
                "offset": QPointF(0, 0),
            },
            1: {
                "sprite": "resources/nodes/button_switch/button_switch_open.png",
                "offset": QPointF(0, 0),
            },
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.node_type = "relay_switch"
        self.properties.setdefault("relay_sensor", None)
        self._init_label()
        # conecta sinais do sensor_registry
        if self.sensor_registry:
            self.sensor_registry.sensor_added.connect(self._on_sensor_registry_changed)
            self.sensor_registry.sensor_removed.connect(self._on_sensor_registry_changed)
            self.sensor_registry.sensor_renamed.connect(self._on_sensor_renamed)

    def initialize_anchors(self):
        # Posicionamento similar ao ButtonSwitch, pode ajustar conforme o sprite
        self.add_anchor(AnchorItem("T", QPointF(self.width*39/50, 0), node=self, domain=self.domain))
        self.add_anchor(AnchorItem("B", QPointF(self.width*39/50, self.height), node=self, domain=self.domain))


    def _init_label(self):
        self.remove_label("relay_sensor_name")
        sensor_name = self.properties.get("relay_sensor")

        label = LabelItem(
            properties={
                "text": sensor_name or "",
                "editable": False,
                "border": False,
                "max_length": 3
            }
        )

        # posiciona à esquerda e centrado verticalmente
        x = -label.boundingRect().width() - 10
        y = self.height / 2 - label.boundingRect().height() / 2
        label.setPos(QPointF(x, y))

        self.add_label("relay_sensor_name", label)

    # --------------------------
    # Menu específico para relay
    # --------------------------
    def extend_context_menu(self, menu: QMenu):
        super().extend_context_menu(menu)

        if self.sensor_registry:
            relay_signals = self.sensor_registry.list_names(sensor_type="relay_coil")
            if relay_signals:
                menu.addSeparator()
                for sensor_name in relay_signals:
                    action = QAction(sensor_name, menu, checkable=True)

                    # marcar se já está associado
                    is_checked = (
                        getattr(self, "current_relay", None) == sensor_name
                    )
                    action.setChecked(is_checked)

                    action.triggered.connect(
                        lambda _, n=sensor_name: self.set_relay_sensor(n)
                    )
                    menu.addAction(action)

    def set_relay_sensor(self, sensor_name: str | None):
        old_sensor = self.properties.get("relay_sensor")
        if old_sensor == sensor_name:
            return

        self.properties["relay_sensor"] = sensor_name

        # atualiza label
        label = self.labels.get("relay_sensor_name")
        if label:
            label.set_text(sensor_name or "")

        self.update()

    def apply_properties(self):
        """
        Atualiza o switch com os valores de properties.
        Especialmente usado ao carregar/instanciar.
        """
        self._init_label()
        self.update()

    # --------------------------
    # Atualiza o sensor selecionado manualmente
    # --------------------------
    def _set_relay_sensor_name(self, new_name: str):
        old_name = self.properties.get("relay_sensor")
        if not new_name or new_name == old_name:
            return

        # valida existência no registry
        if self.sensor_registry and not self.sensor_registry.exists(new_name):
            # volta ao antigo
            label = self.labels.get("relay_sensor_name")
            if label:
                label.set_text(old_name or "")
            return

        self.properties["relay_sensor"] = new_name
        label = self.labels.get("relay_sensor_name")
        if label:
            label.set_text(new_name)

    # --------------------------
    # Tratamento quando sensores são removidos do registry
    # --------------------------
    def _on_sensor_registry_changed(self, *args):
        changed = False
        current_sensor = self.properties.get("relay_sensor")
        if current_sensor and self.sensor_registry and not self.sensor_registry.exists(current_sensor):
            # sensor sumiu → desassocia
            self.properties["relay_sensor"] = None
            changed = True

        if changed:
            self._init_label()
            self.update()

    # --------------------------
    # Tratamento de renomeação de sensor
    # --------------------------
    def _on_sensor_renamed(self, old_name, new_name, node):
        current_sensor = self.properties.get("relay_sensor")
        if current_sensor == old_name:
            self.properties["relay_sensor"] = new_name
            label = self.labels.get("relay_sensor_name")
            if label:
                label.set_text(new_name)
            self.update()