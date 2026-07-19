import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.fixed_displacement_motor import FixedDisplacementMotor
from simulation.nodes.fixed_displacement_motor import FixedDisplacementMotor as FixedDisplacementMotorNode


def test_palette_meta():
    meta = FixedDisplacementMotor.palette_meta()
    assert meta.domains == ("hydraulic",)
    assert meta.name == "Fixed Displacement Motor"


def test_simulation_cls_linkage():
    assert FixedDisplacementMotor.simulation_cls is FixedDisplacementMotorNode


def test_anchors_a_top_b_bottom_same_x_as_pump():
    node = FixedDisplacementMotor(domain="hydraulic")
    assert set(node.anchors.keys()) == {"A", "B"}
    assert node.anchors["A"].pos().y() == 0
    assert node.anchors["B"].pos().y() == node.height
    assert node.anchors["A"].pos().x() == node.anchors["B"].pos().x()


def test_output_label_created_on_setup():
    node = FixedDisplacementMotor(domain="hydraulic")
    assert hasattr(node, "_label_output")


def test_dialog_shows_t_load_field_hidden_when_speed_mode():
    node = FixedDisplacementMotor(domain="hydraulic")
    node.properties["control_mode"] = "speed"
    dialog = node.build_properties_dialog()

    form = dialog._form_layout
    t_visible = None
    omega_visible = None
    for row in range(form.rowCount()):
        item = form.itemAt(row, form.ItemRole.FieldRole)
        if not item:
            continue
        widget = item.widget()
        if widget is dialog._field_t:
            t_visible = form.isRowVisible(row)
        elif widget is dialog._field_omega:
            omega_visible = form.isRowVisible(row)

    assert t_visible is False
    assert omega_visible is True


def test_apply_properties_from_dialog_torque_mode_clears_omega_target():
    node = FixedDisplacementMotor(domain="hydraulic")
    dialog = node.build_properties_dialog()
    dialog._field_d.setText("1.5e-6")
    dialog._combo_mode.setCurrentText("torque")
    dialog._field_t.setText("50")

    node.apply_properties_from_dialog(dialog)

    assert node.properties["D"] == 1.5e-6
    assert node.properties["control_mode"] == "torque"
    assert node.properties["T_load"] == 50.0
    assert node.properties["omega_target"] is None
