import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from unittest.mock import patch
from main_window.main_window import MainWindow
from main_window.language import language_manager


def test_language_change_triggers_main_window_retranslate():
    window = MainWindow()
    try:
        with patch.object(window, "retranslate_ui") as mock_retranslate:
            language_manager.language_changed.emit("en")
            mock_retranslate.assert_called_once()
    finally:
        window.close()


def test_main_window_exposes_menus_dict():
    window = MainWindow()
    try:
        assert set(window.menus) == {"file", "edit", "view", "help", "language"}
    finally:
        window.close()
