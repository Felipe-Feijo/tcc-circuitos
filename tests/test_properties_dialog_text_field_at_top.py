import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from graphics.utils.properties_dialog import PropertiesDialog


def test_text_field_at_top_is_inserted_before_existing_fields():
    dialog = PropertiesDialog(title="Test")
    dialog.add_text_field("K", value="first")
    dialog.add_text_field("Name", value="second", at_top=True)

    assert dialog._form_layout.itemAt(0, dialog._form_layout.ItemRole.FieldRole).widget().text() == "second"
    assert dialog._form_layout.itemAt(1, dialog._form_layout.ItemRole.FieldRole).widget().text() == "first"
