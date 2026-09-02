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


def test_output_label_switches_to_torque_immediately_after_confirming_speed_mode():
    """Regressão: antes, o label só trocava de rótulo (ω <-> T) quando a
    simulação rodava de fato -- confirmando o diálogo, ficava preso no
    texto do modo anterior até lá."""
    node = FixedDisplacementMotor(domain="hydraulic")
    assert node._label_output.toPlainText().startswith("ω")

    dialog = node.build_properties_dialog()
    dialog._field_d.setText("1.5e-6")
    dialog._combo_mode.setCurrentText("Speed")
    dialog._field_omega.setText("100")

    node.apply_properties_from_dialog(dialog)

    assert node._label_output.toPlainText().startswith("T")


def test_output_label_matches_mode_after_apply_properties():
    """Mesma correção pro caminho de carregar um circuito salvo
    (apply_properties(), chamado pelo from_dict)."""
    node = FixedDisplacementMotor(domain="hydraulic")
    node.properties["control_mode"] = "speed"
    node.apply_properties()
    assert node._label_output.toPlainText().startswith("T")


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


def test_dialog_has_optional_p_max_and_n_max_fields():
    node = FixedDisplacementMotor(domain="hydraulic")
    dialog = node.build_properties_dialog()
    assert dialog._field_p_max is not None
    assert dialog._field_n_max is not None


def test_apply_properties_from_dialog_saves_p_max_and_n_max():
    node = FixedDisplacementMotor(domain="hydraulic")
    dialog = node.build_properties_dialog()
    dialog._field_d.setText("1.5e-6")
    dialog._combo_mode.setCurrentText("Torque")
    dialog._field_t.setText("50")
    dialog._field_p_max.setText("1e8")
    dialog._field_n_max.setText("300")

    node.apply_properties_from_dialog(dialog)

    assert node.properties["P_max"] == 1e8
    assert node.properties["n_max"] == 300.0


def test_apply_properties_from_dialog_leaves_p_max_none_when_empty():
    node = FixedDisplacementMotor(domain="hydraulic")
    dialog = node.build_properties_dialog()
    dialog._field_d.setText("1.5e-6")
    dialog._combo_mode.setCurrentText("Torque")
    dialog._field_t.setText("50")

    node.apply_properties_from_dialog(dialog)

    assert node.properties["P_max"] is None
    assert node.properties["n_max"] is None


def test_preview_shows_required_delta_p_in_torque_mode():
    node = FixedDisplacementMotor(domain="hydraulic")
    dialog = node.build_properties_dialog()
    dialog._field_d.setText("1.5e-6")
    dialog._combo_mode.setCurrentText("Torque")
    dialog._field_t.setText("60")

    assert "Required Δp" in dialog._preview_label.text()
    assert "4e+07" in dialog._preview_label.text()  # 60 / 1.5e-6 = 4e7


def test_preview_shows_required_flow_in_speed_mode():
    node = FixedDisplacementMotor(domain="hydraulic")
    dialog = node.build_properties_dialog()
    dialog._field_d.setText("1.5e-6")
    dialog._combo_mode.setCurrentText("Speed")
    dialog._field_omega.setText("100")

    assert "Required flow rate" in dialog._preview_label.text()
    assert "0.00015" in dialog._preview_label.text()  # 1.5e-6 * 100 = 1.5e-4


def test_preview_shows_placeholder_when_fields_incomplete():
    node = FixedDisplacementMotor(domain="hydraulic")
    dialog = node.build_properties_dialog()
    assert dialog._preview_label.text() == "—"


def test_ok_button_enabled_after_filling_only_the_field_for_current_mode():
    """Regressão: T_load/omega_target sendo required=True nos dois travava
    o OK mesmo preenchendo só o campo do modo atual, porque a validação
    olha todo campo numérico obrigatório, visível ou não."""
    node = FixedDisplacementMotor(domain="hydraulic")
    dialog = node.build_properties_dialog()

    dialog._field_d.setText("1.5e-6")
    dialog._combo_mode.setCurrentText("Torque")
    dialog._field_t.setText("50")
    # omega_target fica vazio (escondido, não se aplica no modo torque)

    assert dialog._ok_btn.isEnabled() is True


def test_apply_properties_from_dialog_torque_mode_clears_omega_target():
    node = FixedDisplacementMotor(domain="hydraulic")
    dialog = node.build_properties_dialog()
    dialog._field_d.setText("1.5e-6")
    dialog._combo_mode.setCurrentText("Torque")
    dialog._field_t.setText("50")

    node.apply_properties_from_dialog(dialog)

    assert node.properties["D"] == 1.5e-6
    assert node.properties["control_mode"] == "torque"
    assert node.properties["T_load"] == 50.0
    assert node.properties["omega_target"] is None
