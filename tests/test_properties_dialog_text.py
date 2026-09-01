import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from graphics.utils.properties_dialog import PropertiesDialog
from graphics.utils.defect_dialog import DefectDialog


def test_default_title_is_translated_at_construction_not_at_import():
    dialog = PropertiesDialog()
    try:
        assert dialog.windowTitle() == "Properties"
    finally:
        dialog.close()

    custom = PropertiesDialog(title="Custom Title")
    try:
        assert custom.windowTitle() == "Custom Title"
    finally:
        custom.close()


def test_dialog_buttons_are_english():
    dialog = PropertiesDialog()
    try:
        assert dialog._cancel_btn.text() == "Cancel"
        assert dialog._ok_btn.text() == "OK"
    finally:
        dialog.close()


def test_defect_dialog_default_title_and_buttons_are_english():
    dialog = DefectDialog()
    try:
        assert dialog.windowTitle() == "Simulate defect"
        assert dialog._ok_btn.text() == "Apply"
        assert dialog._restore_btn.text() == "Restore"
    finally:
        dialog.close()
