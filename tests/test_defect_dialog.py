import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QDialog

app = QApplication.instance() or QApplication([])

from graphics.utils.defect_dialog import DefectDialog


def test_ok_button_relabeled_to_aplicar():
    dialog = DefectDialog(title="Test")
    assert dialog._ok_btn.text() == "Apply"


def test_has_three_buttons_in_order_cancelar_restaurar_aplicar():
    dialog = DefectDialog(title="Test")
    labels = [
        dialog._btn_layout.itemAt(i).widget().text()
        for i in range(dialog._btn_layout.count())
        if dialog._btn_layout.itemAt(i).widget() is not None
    ]
    assert labels == ["Cancel", "Restore", "Apply"]


def test_restore_requested_defaults_to_false():
    dialog = DefectDialog(title="Test")
    assert dialog.restore_requested is False


def test_clicking_restore_sets_flag_and_accepts_without_validation():
    dialog = DefectDialog(title="Test")
    # required field left empty -- normal OK/Apply validation would fail here
    dialog.add_number_field("K", value=None, required=True)
    dialog._restore_btn.click()
    assert dialog.restore_requested is True
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_aplicar_disabled_when_min_value_field_at_min():
    dialog = DefectDialog(title="Test")
    field = dialog.add_number_field("K", required=True, min_value=0)
    field.setText("0")
    dialog._refresh_ok_button()
    assert dialog._ok_btn.isEnabled() is False


def test_aplicar_enabled_when_min_value_field_above_min():
    dialog = DefectDialog(title="Test")
    field = dialog.add_number_field("K", required=True, min_value=0)
    field.setText("0.001")
    dialog._refresh_ok_button()
    assert dialog._ok_btn.isEnabled() is True
