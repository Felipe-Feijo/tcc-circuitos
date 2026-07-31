import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.coil.solenoid_coil import SolenoidCoil
from graphics.sensor_registry.sensor_registry import SensorRegistry


def test_apply_properties_after_reload_keeps_loaded_sensor_name():
    registry = SensorRegistry()
    node = SolenoidCoil(domain="electric", sensor_registry=registry)

    # Simula o que NodeItem.from_dict faz: substitui node.properties por um
    # dict novo carregado do arquivo, sem reatribuir node.sensors.
    node.properties = {"sensor": {"coil": {"name": "Y7"}}}
    node.apply_properties()

    assert registry.exists("Y7")
    assert node.sensors["coil"]["name"] == "Y7"
