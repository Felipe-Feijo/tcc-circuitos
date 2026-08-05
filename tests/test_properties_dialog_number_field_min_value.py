import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.utils.properties_dialog import PropertiesDialog


def test_number_field_without_min_value_accepts_zero_and_negative():
    dialog = PropertiesDialog(title="Test")
    field = dialog.add_number_field("K", required=True)
    field.setText("0")
    assert dialog._validate_field(field) is True
    field.setText("-5")
    assert dialog._validate_field(field) is True


def test_number_field_with_min_value_rejects_value_equal_to_min():
    dialog = PropertiesDialog(title="Test")
    field = dialog.add_number_field("K", required=True, min_value=0)
    field.setText("0")
    assert dialog._validate_field(field) is False
    assert "red" in field.styleSheet()


def test_number_field_with_min_value_rejects_value_below_min():
    dialog = PropertiesDialog(title="Test")
    field = dialog.add_number_field("K", required=True, min_value=0)
    field.setText("-5")
    assert dialog._validate_field(field) is False
    assert "red" in field.styleSheet()


def test_number_field_with_min_value_accepts_value_above_min():
    dialog = PropertiesDialog(title="Test")
    field = dialog.add_number_field("K", required=True, min_value=0)
    field.setText("0.001")
    assert dialog._validate_field(field) is True
    assert field.styleSheet() == ""


def test_ok_button_disabled_when_min_value_violated():
    dialog = PropertiesDialog(title="Test")
    field = dialog.add_number_field("K", required=True, min_value=0)
    field.setText("0")
    dialog._refresh_ok_button()
    assert dialog._ok_btn.isEnabled() is False


def test_ok_button_enabled_when_min_value_satisfied():
    dialog = PropertiesDialog(title="Test")
    field = dialog.add_number_field("K", required=True, min_value=0)
    field.setText("0.001")
    dialog._refresh_ok_button()
    assert dialog._ok_btn.isEnabled() is True
