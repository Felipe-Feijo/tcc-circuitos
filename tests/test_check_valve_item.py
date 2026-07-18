import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.check_valve.check_valve import CheckValve
from simulation.nodes.check_valve.check_valve import CheckValve as CheckValveNode


def test_default_anchors_are_x_and_y_only():
    node = CheckValve(domain="pneumatic")
    assert set(node.anchors.keys()) == {"X", "Y"}


def test_x_and_y_positions_match_sprite():
    node = CheckValve(domain="pneumatic")
    assert (node.anchors["X"].pos().x(), node.anchors["X"].pos().y()) == (0, 75)
    assert (node.anchors["Y"].pos().x(), node.anchors["Y"].pos().y()) == (150, 75)


def test_palette_meta():
    meta = CheckValve.palette_meta()
    assert meta.domains == ("pneumatic",)
    assert meta.name == "Check Valve"
    assert meta.sprite.endswith("check_valve_closed.png")


def test_default_pixmap_is_closed():
    node = CheckValve(domain="pneumatic")
    assert node.pixmap is node._pixmap_closed


def test_simulation_cls_linkage():
    assert CheckValve.simulation_cls is CheckValveNode


def test_node_type():
    assert CheckValve.node_type == "check_valve"


def test_piloted_true_adds_z_anchor_unmirrored_by_default():
    node = CheckValve(domain="pneumatic")
    node.properties["piloted"] = True
    node.apply_properties()

    assert "Z" in node.anchors
    assert (node.anchors["Z"].pos().x(), node.anchors["Z"].pos().y()) == (150, 42)
    assert node._pilot_overlay is not None


def test_pilot_mirrored_moves_z_anchor():
    node = CheckValve(domain="pneumatic")
    node.properties["piloted"] = True
    node.properties["pilot_mirrored"] = True
    node.apply_properties()

    assert (node.anchors["Z"].pos().x(), node.anchors["Z"].pos().y()) == (150, 108)


def test_toggling_piloted_back_to_false_removes_z_anchor():
    node = CheckValve(domain="pneumatic")
    node.properties["piloted"] = True
    node.apply_properties()
    assert "Z" in node.anchors

    node.properties["piloted"] = False
    node.apply_properties()
    assert "Z" not in node.anchors
    assert node._pilot_overlay is None


def test_update_from_domain_switches_pixmap_to_closed():
    node = CheckValve(domain="pneumatic")

    class FakeDomainNode:
        anchors = {}
        def get_visual_state(self):
            return "closed"

    node.update_from_domain(FakeDomainNode())
    assert node.pixmap is node._pixmap_closed


def test_update_from_domain_switches_pixmap_to_open():
    node = CheckValve(domain="pneumatic")
    node.pixmap = node._pixmap_closed

    class FakeDomainNode:
        anchors = {}
        def get_visual_state(self):
            return "open"

    node.update_from_domain(FakeDomainNode())
    assert node.pixmap is node._pixmap_open


def test_reset_visual_state_restores_closed_pixmap():
    node = CheckValve(domain="pneumatic")
    node.pixmap = node._pixmap_open
    node.reset_visual_state()
    assert node.pixmap is node._pixmap_closed


def test_build_properties_dialog_reflects_current_properties():
    node = CheckValve(domain="pneumatic")
    node.properties["piloted"] = True
    node.properties["pilot_mirrored"] = True

    dialog = node.build_properties_dialog()

    assert dialog._field_piloted.isChecked() is True
    assert dialog._field_pilot_mirrored.isChecked() is True


def test_apply_properties_from_dialog_updates_properties_and_anchors():
    node = CheckValve(domain="pneumatic")
    dialog = node.build_properties_dialog()
    dialog._field_piloted.setChecked(True)
    dialog._field_pilot_mirrored.setChecked(True)

    node.apply_properties_from_dialog(dialog)

    assert node.properties["piloted"] is True
    assert node.properties["pilot_mirrored"] is True
    assert "Z" in node.anchors
    assert (node.anchors["Z"].pos().x(), node.anchors["Z"].pos().y()) == (150, 108)


def test_pilot_mirrored_row_hidden_when_not_piloted():
    node = CheckValve(domain="pneumatic")
    dialog = node.build_properties_dialog()

    form = dialog._form_layout
    row_visible = None
    for row in range(form.rowCount()):
        item = form.itemAt(row, form.ItemRole.FieldRole)
        if item and item.widget() is dialog._field_pilot_mirrored:
            row_visible = form.isRowVisible(row)
            break
    assert row_visible is False


def test_pilot_mirrored_row_visible_when_piloted():
    node = CheckValve(domain="pneumatic")
    node.properties["piloted"] = True
    dialog = node.build_properties_dialog()

    form = dialog._form_layout
    row_visible = None
    for row in range(form.rowCount()):
        item = form.itemAt(row, form.ItemRole.FieldRole)
        if item and item.widget() is dialog._field_pilot_mirrored:
            row_visible = form.isRowVisible(row)
            break
    assert row_visible is True
