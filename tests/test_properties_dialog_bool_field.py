import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QCheckBox, QFormLayout

app = QApplication.instance() or QApplication([])

from graphics.utils.properties_dialog import PropertiesDialog


def test_add_bool_field_returns_checkbox():
    dialog = PropertiesDialog(title="Test")
    field = dialog.add_bool_field("Piloted")
    assert isinstance(field, QCheckBox)


def test_add_bool_field_defaults_to_false():
    dialog = PropertiesDialog(title="Test")
    field = dialog.add_bool_field("Piloted")
    assert field.isChecked() is False


def test_add_bool_field_respects_initial_value():
    dialog = PropertiesDialog(title="Test")
    field = dialog.add_bool_field("Piloted", value=True)
    assert field.isChecked() is True


def test_add_bool_field_adds_form_row():
    dialog = PropertiesDialog(title="Test")
    rows_before = dialog._form_layout.rowCount()
    dialog.add_bool_field("Piloted")
    assert dialog._form_layout.rowCount() == rows_before + 1
