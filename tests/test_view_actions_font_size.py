# tests/test_view_actions_font_size.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from unittest.mock import Mock
from main_window.actions.view_actions import create_view_actions


def test_font_size_action_exists_and_triggers_handler():
    fake_main_window = Mock()
    fake_main_window.tr = lambda s: s  # identity translation, no .qm installed
    actions = create_view_actions(fake_main_window)

    assert "font_size" in actions
    assert actions["font_size"].text() == "Font Size..."

    actions["font_size"].trigger()
    fake_main_window.on_change_font_size.assert_called_once()
