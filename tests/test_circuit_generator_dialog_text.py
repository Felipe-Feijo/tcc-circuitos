import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from main_window.ui.circuit_generator_dialog import CircuitGeneratorDialog


def test_dialog_labels_are_english():
    dialog = CircuitGeneratorDialog()
    try:
        assert dialog.windowTitle() == "New from Sequence"
        assert dialog._btn_cancel.text() == "Cancel"
        assert dialog._btn_generate.text() == "Generate"
        assert dialog._rb_cascade.text() == "Cascade"
        assert dialog._rb_step.text() == "Step by Step"
        assert dialog._rb_pneumatic.text() == "Pneumatic"
        assert dialog._rb_electric.text() == "Electric"
    finally:
        dialog.close()


def test_empty_sequence_error_is_english():
    dialog = CircuitGeneratorDialog()
    try:
        assert dialog._validate_sequence("") == "Enter a sequence."
    finally:
        dialog.close()
