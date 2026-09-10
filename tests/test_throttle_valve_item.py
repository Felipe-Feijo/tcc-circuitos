import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.throttle_valve import ThrottleValve
from simulation.nodes.throttle_valve import ThrottleValve as ThrottleValveNode


def test_default_anchors_are_x_and_y_only():
    node = ThrottleValve(domain="hydraulic")
    assert set(node.anchors.keys()) == {"X", "Y"}


def test_x_and_y_positions_match_sprite():
    node = ThrottleValve(domain="hydraulic")
    assert (node.anchors["X"].pos().x(), node.anchors["X"].pos().y()) == (0, node.height / 2)
    assert (node.anchors["Y"].pos().x(), node.anchors["Y"].pos().y()) == (node.width, node.height / 2)


def test_sprite_loaded_from_disk():
    node = ThrottleValve(domain="hydraulic")
    assert node.width > 0
    assert node.height > 0


def test_palette_meta():
    meta = ThrottleValve.palette_meta()
    assert meta.domains == ("hydraulic",)
    assert meta.name == "Throttle Valve"
    assert meta.sprite.endswith("throttle_valve.png")


def test_simulation_cls_linkage():
    assert ThrottleValve.simulation_cls is ThrottleValveNode


def test_node_type():
    assert ThrottleValve.node_type == "throttle_valve"


def test_build_properties_dialog_reflects_current_k():
    node = ThrottleValve(domain="hydraulic")
    node.properties["k"] = 1.5e-8

    dialog = node.build_properties_dialog()

    assert dialog._field_k.text() == "1.5e-08"


def test_apply_properties_from_dialog_updates_k():
    node = ThrottleValve(domain="hydraulic")
    dialog = node.build_properties_dialog()
    dialog._field_k.setText("2e-7")

    node.apply_properties_from_dialog(dialog)

    assert node.properties["k"] == 2e-7
