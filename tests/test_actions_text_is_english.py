# tests/test_actions_text_is_english.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from unittest.mock import Mock
from main_window.actions import create_actions, retranslate_actions


class _FakeMainWindow(QObject):
    """Stands in for MainWindow in these factories.

    A plain unittest.mock.Mock cannot be used here: several action
    factories (file/edit/mode/help/simulation/generator) parent their
    QAction/QActionGroup to `main_window`, and PyQt requires a real
    QObject for that -- not a Mock. This is a genuine QObject (so
    parenting works) that falls back to a Mock for every attribute it
    doesn't itself define (handler methods, .state, .clipboard_manager,
    etc., all only referenced lazily by the connected callbacks, never
    called during action construction).

    A plain Mock() would also auto-vivify a truthy child Mock for any
    attribute access, including ones retranslate_actions probes with
    getattr(..., default)/hasattr to detect *absence* of optional state
    (simulation, use_light_theme, update_simulation_actions) -- so those
    specific names are excluded from the fallback and raise AttributeError
    normally unless a test sets them explicitly.
    """

    _NOT_AUTO_MOCKED = {"simulation", "use_light_theme", "update_simulation_actions"}

    def __init__(self):
        super().__init__()
        self._mock = Mock()

    def tr(self, source: str) -> str:  # identity translation, no .qm installed
        return source

    def __getattr__(self, name):
        if name in self._NOT_AUTO_MOCKED:
            raise AttributeError(name)
        return getattr(self._mock, name)


def _build_actions():
    fake_main_window = _FakeMainWindow()
    return create_actions(fake_main_window), fake_main_window


def test_action_texts_are_english_source_strings():
    actions, _ = _build_actions()

    assert actions["new"].text() == "New"
    assert actions["open"].text() == "Open"
    assert actions["save"].text() == "Save"
    assert actions["save_as"].text() == "Save As"
    assert actions["exit"].text() == "Exit"
    assert actions["zoom_in"].text() == "Zoom In"
    assert actions["zoom_out"].text() == "Zoom Out"
    assert actions["zoom_fit"].text() == "Fit to Contents"
    assert actions["toggle_theme"].text() == "Light Theme"
    assert actions["font_size"].text() == "Font Size..."
    assert actions["delete"].text() == "Delete"
    assert actions["copy"].text() == "Copy"
    assert actions["paste"].text() == "Paste"
    assert actions["open_palette"].text() == "Add"
    assert actions["undo"].text() == "Undo"
    assert actions["redo"].text() == "Redo"
    assert actions["rotate"].text() == "Rotate 90°"
    assert actions["mode_select"].text() == "Select"
    assert actions["mode_connect"].text() == "Connect"
    assert actions["mode_simulate"].text() == "Simulate"
    assert actions["about"].text() == "About"
    assert actions["run"].text() == "Run"
    assert actions["step_back"].text() == "Step Back"
    assert actions["step_forward"].text() == "Step Forward"
    assert actions["new_from_sequence"].text() == "New from Sequence..."


def test_retranslate_actions_reapplies_static_text():
    actions, fake_main_window = _build_actions()
    actions["new"].setText("stale")

    retranslate_actions(actions, fake_main_window)

    assert actions["new"].text() == "New"


def test_retranslate_actions_reformats_dt_from_current_simulation_state():
    actions, fake_main_window = _build_actions()
    fake_main_window.simulation = Mock(dt=0.25)

    retranslate_actions(actions, fake_main_window)

    assert actions["dt"].text() == "dt: 0.250s"


def test_retranslate_actions_reapplies_toggle_theme_text_from_current_state():
    actions, fake_main_window = _build_actions()
    fake_main_window.use_light_theme = True

    retranslate_actions(actions, fake_main_window)

    assert actions["toggle_theme"].text() == "Dark Theme"
