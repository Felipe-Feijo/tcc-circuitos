"""Nó gráfico de contato de relé (NA/NF controlado por bobina)."""

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu
from simulation.nodes.switch.relay_switch import RelaySwitch as RelaySwitchNode

from graphics.items.base.nodes.switch.switch_item import SwitchItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.labels.label import LabelItem
from .....anchors.anchor import AnchorItem


class RelaySwitch(SwitchItem):
    node_type = "relay_switch"
    simulation_cls = RelaySwitchNode
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
                "sprite": "resources/nodes/relay_switch/relay_switch_nc_closed.png",
                "offset": QPointF(0, 0),
            },
            1: {
                "sprite": "resources/nodes/relay_switch/relay_switch_nc_open.png",
                "offset": QPointF(0, 0),
            },
        }
    }

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("electric",),
            sprite=cls.SWITCH_VISUALS["NO"][0]["sprite"],
            name="RelaySwitch",
        )

    def setup(self) -> None:
        super().setup()  # SwitchItem.setup()
        self.properties.setdefault("relay_sensor", None)
        self._init_label()

    def register_sensors(self) -> None:
        if self.sensor_registry:
            self.sensor_registry.sensor_added.connect(self._on_sensor_registry_changed)
            self.sensor_registry.sensor_removed.connect(self._on_sensor_registry_changed)
            self.sensor_registry.sensor_renamed.connect(self._on_sensor_renamed)

    def initialize_anchors(self):
        # Posicionamento similar ao ButtonSwitch, pode ajustar conforme o sprite
        self.add_anchor(AnchorItem("T", QPointF(self.width*39/50, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))
        self.add_anchor(AnchorItem("B", QPointF(self.width*39/50, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))


    def _init_label(self):
        self.remove_label("relay_sensor_name")
        sensor_name = self.properties.get("relay_sensor")

        label = LabelItem(
            properties={
                "text": sensor_name or "",
                "editable": False,
                "movable": False,
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

    def build_properties_dialog(self):
        from graphics.utils.properties_dialog import PropertiesDialog
        dialog = PropertiesDialog(title="Relay Switch — Properties")

        current_type = self.properties.get("contact_type", "NO")
        dialog._combo_contact = dialog.add_combo_field(
            "Tipo de contato", ["NO", "NC"], current=current_type
        )

        relay_signals = []
        if self.sensor_registry:
            relay_signals = self.sensor_registry.list_names(sensor_type="relay_coil")

        current_sensor = self.properties.get("relay_sensor") or ""
        options = ["(nenhum)"] + relay_signals
        current_option = current_sensor if current_sensor in relay_signals else "(nenhum)"
        dialog._combo_relay = dialog.add_combo_field(
            "Sensor de relé", options, current=current_option
        )

        return dialog

    def apply_properties_from_dialog(self, dialog):
        self.set_contact_type(dialog._combo_contact.currentText())
        selected = dialog._combo_relay.currentText()
        self.set_relay_sensor(None if selected == "(nenhum)" else selected)

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