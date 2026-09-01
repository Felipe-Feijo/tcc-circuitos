import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from unittest.mock import Mock, patch
from PyQt6.QtWidgets import QMessageBox
from main_window.report_resolution import resolve_report


def test_asks_english_question_and_discards_on_no():
    with patch("main_window.report_resolution.QMessageBox.question", return_value=QMessageBox.StandardButton.No) as mock_question:
        with patch("main_window.report_resolution.shutil.rmtree") as mock_rmtree:
            resolve_report(parent=None, report_dir="/tmp/report", circuit_name="circuit")

    assert mock_question.call_args.args[1] == "Simulation report"
    mock_rmtree.assert_called_once()
