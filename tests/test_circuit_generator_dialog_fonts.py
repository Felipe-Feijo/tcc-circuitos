# tests/test_circuit_generator_dialog_fonts.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QLabel
app = QApplication.instance() or QApplication([])

from main_window.ui.circuit_generator_dialog import CircuitGeneratorDialog


def test_hint_and_error_labels_use_13px_font():
    dialog = CircuitGeneratorDialog()
    labels_with_font_size = [
        lbl for lbl in dialog.findChildren(QLabel)
        if "font-size" in lbl.styleSheet()
    ]
    assert len(labels_with_font_size) == 2
    for lbl in labels_with_font_size:
        assert "13px" in lbl.styleSheet()
        assert "11px" not in lbl.styleSheet()
