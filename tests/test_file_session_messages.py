import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from unittest.mock import Mock, patch
from persistence.file_session import SceneFileSession


def test_open_shows_english_error_title_on_failure():
    parent = Mock()
    session = SceneFileSession(scene=Mock(), parent_window=parent, editor_state=Mock())

    with patch("persistence.file_session.QFileDialog.getOpenFileName", return_value=("bad.json", "")):
        with patch("persistence.serializer.load_from_file", side_effect=ValueError("boom")):
            with patch("persistence.file_session.QMessageBox.critical") as mock_critical:
                session.open()

    assert mock_critical.call_args.args[1] == "Error opening file"


def test_window_title_uses_english_prefix_after_save():
    parent = Mock()
    session = SceneFileSession(scene=Mock(), parent_window=parent, editor_state=Mock())

    with patch("persistence.serializer.save_to_file"):
        session._save_to_path("some/path/circuit.json")

    parent.setWindowTitle.assert_called_once_with("Circuit Editor – circuit.json")
