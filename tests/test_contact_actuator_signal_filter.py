import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.switch.contact import Contact
from graphics.sensor_registry.sensor_registry import SensorRegistry


def _combo_items(combo):
    return [combo.itemText(i) for i in range(combo.count())]


def test_dialog_lists_relay_coil_sensors():
    registry = SensorRegistry()
    registry.register("K1", "relay_coil", node=object())

    node = Contact(domain="electric", sensor_registry=registry)
    dialog = node.build_properties_dialog()

    assert "K1" in _combo_items(dialog._combo_relay)


def test_dialog_lists_cylinder_end_sensors():
    registry = SensorRegistry()
    registry.register("a1", "cylinder_end", node=object())

    node = Contact(domain="electric", sensor_registry=registry)
    dialog = node.build_properties_dialog()

    assert "a1" in _combo_items(dialog._combo_relay)


def test_dialog_excludes_unrelated_sensor_types():
    registry = SensorRegistry()
    registry.register("R1", "reed", node=object())

    node = Contact(domain="electric", sensor_registry=registry)
    dialog = node.build_properties_dialog()

    assert "R1" not in _combo_items(dialog._combo_relay)


def test_dialog_lists_solenoid_coil_sensors():
    registry = SensorRegistry()
    registry.register("Y1", "solenoid_coil", node=object())

    node = Contact(domain="electric", sensor_registry=registry)
    dialog = node.build_properties_dialog()

    assert "Y1" in _combo_items(dialog._combo_relay)


def test_dialog_lists_both_types_together_sorted():
    registry = SensorRegistry()
    registry.register("K1", "relay_coil", node=object())
    registry.register("a1", "cylinder_end", node=object())

    node = Contact(domain="electric", sensor_registry=registry)
    dialog = node.build_properties_dialog()

    items = _combo_items(dialog._combo_relay)
    assert "K1" in items and "a1" in items
