import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.pressure_reducing_valve import PressureReducingValve
from simulation.nodes.pressure_reducing_valve import PressureReducingValve as PressureReducingValveNode


def test_default_anchors_are_p_and_a_only():
    node = PressureReducingValve(domain="hydraulic")
    assert set(node.anchors.keys()) == {"P", "A"}


def test_p_and_a_positions_match_sprite():
    node = PressureReducingValve(domain="hydraulic")
    w, h = node.width, node.height
    assert (node.anchors["P"].pos().x(), node.anchors["P"].pos().y()) == (w * 98.5 / 200, 0)
    assert (node.anchors["A"].pos().x(), node.anchors["A"].pos().y()) == (w * 98.5 / 200, h)


def test_palette_meta():
    meta = PressureReducingValve.palette_meta()
    assert meta.domains == ("hydraulic",)
    assert meta.name == "Pressure Reducing Valve"
    assert meta.sprite.endswith("pressure_reducing_valve.png")


def test_simulation_cls_linkage():
    assert PressureReducingValve.simulation_cls is PressureReducingValveNode


def test_node_type():
    assert PressureReducingValve.node_type == "pressure_reducing_valve"


def test_build_properties_dialog_reflects_current_properties():
    node = PressureReducingValve(domain="hydraulic")
    node.properties["p_set"] = 1.5e7

    dialog = node.build_properties_dialog()

    assert dialog._field_p_set.text() == "15000000.0"


def test_apply_properties_from_dialog_updates_properties():
    node = PressureReducingValve(domain="hydraulic")
    dialog = node.build_properties_dialog()
    dialog._field_p_set.setText("2e7")

    node.apply_properties_from_dialog(dialog)

    assert node.properties["p_set"] == 2e7
