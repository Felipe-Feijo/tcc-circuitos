import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.relief_valve import ReliefValve
from simulation.nodes.relief_valve import ReliefValve as ReliefValveNode


def test_default_anchors_are_p_and_t_only():
    node = ReliefValve(domain="hydraulic")
    assert set(node.anchors.keys()) == {"P", "T"}


def test_p_and_t_positions_match_sprite():
    node = ReliefValve(domain="hydraulic")
    w, h = node.width, node.height
    assert (node.anchors["P"].pos().x(), node.anchors["P"].pos().y()) == (w * 99 / 199, 0)
    assert (node.anchors["T"].pos().x(), node.anchors["T"].pos().y()) == (w * 99 / 199, h)


def test_palette_meta():
    meta = ReliefValve.palette_meta()
    assert meta.domains == ("hydraulic",)
    assert meta.name == "Relief Valve (direct)"
    assert meta.sprite.endswith("relief_valve.png")


def test_simulation_cls_linkage():
    assert ReliefValve.simulation_cls is ReliefValveNode


def test_node_type():
    assert ReliefValve.node_type == "relief_valve"


def test_piloted_false_by_default_no_y_anchor_or_overlay():
    node = ReliefValve(domain="hydraulic")
    assert "Y" not in node.anchors
    assert node._pilot_overlay is None


def test_piloted_true_adds_y_anchor_and_overlay():
    node = ReliefValve(domain="hydraulic")
    node.properties["piloted"] = True
    node.apply_properties()

    assert "Y" in node.anchors
    assert (node.anchors["Y"].pos().x(), node.anchors["Y"].pos().y()) == (node.width, node.height / 2)
    assert node._pilot_overlay is not None


def test_toggling_piloted_back_to_false_removes_y_anchor():
    node = ReliefValve(domain="hydraulic")
    node.properties["piloted"] = True
    node.apply_properties()
    assert "Y" in node.anchors

    node.properties["piloted"] = False
    node.apply_properties()
    assert "Y" not in node.anchors
    assert node._pilot_overlay is None


def test_build_properties_dialog_reflects_current_properties():
    node = ReliefValve(domain="hydraulic")
    node.properties["p_set"] = 1.5e7
    node.properties["piloted"] = True

    dialog = node.build_properties_dialog()

    assert dialog._field_p_set.text() == "15000000.0"
    assert dialog._field_piloted.isChecked() is True


def test_apply_properties_from_dialog_updates_properties_and_anchors():
    node = ReliefValve(domain="hydraulic")
    dialog = node.build_properties_dialog()
    dialog._field_p_set.setText("2e7")
    dialog._field_piloted.setChecked(True)

    node.apply_properties_from_dialog(dialog)

    assert node.properties["p_set"] == 2e7
    assert node.properties["piloted"] is True
    assert "Y" in node.anchors
