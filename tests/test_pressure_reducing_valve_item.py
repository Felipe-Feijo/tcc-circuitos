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


def test_relieving_false_by_default_no_t_anchor_or_overlay():
    node = PressureReducingValve(domain="hydraulic")
    assert "T" not in node.anchors
    assert node._relief_overlay is None


def test_relieving_true_adds_t_anchor_and_overlay():
    node = PressureReducingValve(domain="hydraulic")
    node.properties["relieving"] = True
    node.apply_properties()

    assert "T" in node.anchors
    assert (node.anchors["T"].pos().x(), node.anchors["T"].pos().y()) == (
        node.width * 134.5 / 200, node.height,
    )
    assert node._relief_overlay is not None


def test_toggling_relieving_back_to_false_removes_t_anchor():
    node = PressureReducingValve(domain="hydraulic")
    node.properties["relieving"] = True
    node.apply_properties()
    assert "T" in node.anchors

    node.properties["relieving"] = False
    node.apply_properties()
    assert "T" not in node.anchors
    assert node._relief_overlay is None


def test_build_properties_dialog_reflects_relieving_property():
    node = PressureReducingValve(domain="hydraulic")
    node.properties["p_set"] = 1.5e7
    node.properties["relieving"] = True

    dialog = node.build_properties_dialog()

    assert dialog._field_p_set.text() == "15000000.0"
    assert dialog._field_relieving.isChecked() is True


def test_apply_properties_from_dialog_updates_relieving_and_anchors():
    node = PressureReducingValve(domain="hydraulic")
    dialog = node.build_properties_dialog()
    dialog._field_p_set.setText("2e7")
    dialog._field_relieving.setChecked(True)

    node.apply_properties_from_dialog(dialog)

    assert node.properties["p_set"] == 2e7
    assert node.properties["relieving"] is True
    assert "T" in node.anchors
