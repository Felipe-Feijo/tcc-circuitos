import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from unittest.mock import Mock, patch
from main_window.actions.language_actions import create_language_actions


def test_creates_checkable_mutually_exclusive_language_actions():
    fake_main_window = Mock()
    with patch("main_window.language.get_language", return_value="en"):
        actions = create_language_actions(fake_main_window)

    assert set(actions) == {"language_en", "language_pt_br"}
    assert actions["language_en"].text() == "English"
    assert actions["language_pt_br"].text() == "Português (Brasil)"
    assert actions["language_en"].isCheckable()
    assert actions["language_en"].isChecked()
    assert not actions["language_pt_br"].isChecked()


def test_triggering_pt_br_action_applies_pt_br_language():
    fake_main_window = Mock()
    with patch("main_window.language.get_language", return_value="en"):
        actions = create_language_actions(fake_main_window)

    with patch("main_window.actions.language_actions.apply_language") as mock_apply:
        actions["language_pt_br"].trigger()
        mock_apply.assert_called_once()
        assert mock_apply.call_args.args[1] == "pt_BR"
