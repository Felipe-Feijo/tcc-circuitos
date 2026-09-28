"""DefectDialog declarative fields (DefectFieldSpec)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QCheckBox, QComboBox, QLineEdit

app = QApplication.instance() or QApplication([])

from graphics.utils.defect_dialog import DefectDialog, DefectFieldSpec

_NUMBER = DefectFieldSpec("k", "Conductance", "number", placeholder="ex: 1", min_value=0)
_BOOL = DefectFieldSpec("stuck", "Stuck", "bool")
_CHOICE = DefectFieldSpec(
    "mode", "Mode", "choice",
    options=(("none", "Normal"), ("welded", "Welded"), ("open", "Open")),
)


def test_number_field_prefilled_and_read_back_as_float():
    dialog = DefectDialog()
    field = dialog.add_defect_field(_NUMBER, 2.5e-8)
    assert isinstance(field, QLineEdit)
    assert float(field.text()) == 2.5e-8
    field.setText("3.3e-8")
    assert dialog.defect_values() == {"k": 3.3e-8}


def test_number_field_with_none_value_starts_empty():
    dialog = DefectDialog()
    field = dialog.add_defect_field(_NUMBER, None)
    assert field.text() == ""


def test_number_field_min_value_rejects_zero():
    dialog = DefectDialog()
    field = dialog.add_defect_field(_NUMBER, 1.0)
    field.setText("0")
    dialog._refresh_ok_button()
    assert dialog._ok_btn.isEnabled() is False


def test_bool_field_prefilled_and_read_back():
    dialog = DefectDialog()
    field = dialog.add_defect_field(_BOOL, True)
    assert isinstance(field, QCheckBox)
    assert field.isChecked() is True
    field.setChecked(False)
    assert dialog.defect_values() == {"stuck": False}


def test_bool_field_with_none_value_starts_unchecked():
    dialog = DefectDialog()
    assert dialog.add_defect_field(_BOOL, None).isChecked() is False


def test_choice_field_prefilled_and_read_back_as_option_value():
    dialog = DefectDialog()
    field = dialog.add_defect_field(_CHOICE, "welded")
    assert isinstance(field, QComboBox)
    assert field.currentText() == "Welded"
    field.setCurrentIndex(2)
    assert dialog.defect_values() == {"mode": "open"}


def test_defect_values_covers_every_field_in_order():
    dialog = DefectDialog()
    dialog.add_defect_field(_NUMBER, 1.0)
    dialog.add_defect_field(_BOOL, False)
    dialog.add_defect_field(_CHOICE, "none")
    assert list(dialog.defect_values()) == ["k", "stuck", "mode"]


def test_defect_widget_returns_the_field_by_key():
    dialog = DefectDialog()
    field = dialog.add_defect_field(_BOOL, False)
    assert dialog.defect_widget("stuck") is field


def test_note_text_is_stripped_and_empty_without_note_field():
    dialog = DefectDialog()
    assert dialog.note_text() == ""
    dialog.add_note_field()
    dialog.note_field.setText("  debris  ")
    assert dialog.note_text() == "debris"
