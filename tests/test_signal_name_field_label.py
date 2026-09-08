"""The per-signal name field (cylinder end sensors, coil) is labeled
"Signal name" -- not "Name" -- to avoid confusion with the node's own
display name (NodeItem.name), which now also shows up as "Name" at the
top of every properties dialog."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.cylinder.double_acting_cylinder import DoubleActingCylinder
from graphics.items.base.nodes.coil.relay_coil import RelayCoil
from graphics.sensor_registry.sensor_registry import SensorRegistry


def test_cylinder_sensor_name_field_is_labeled_signal_name():
    node = DoubleActingCylinder(domain="pneumatic", sensor_registry=SensorRegistry())
    dialog = node.build_properties_dialog()

    label = dialog._form_layout.labelForField(dialog._name_retracted)
    assert label.text().strip() == "Signal name"


def test_coil_name_field_is_labeled_signal_name():
    node = RelayCoil(domain="electric", sensor_registry=SensorRegistry())
    dialog = node.build_properties_dialog()

    label = dialog._form_layout.labelForField(dialog._name_field)
    assert label.text() == "Signal name"
