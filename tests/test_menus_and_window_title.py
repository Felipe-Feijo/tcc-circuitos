# tests/test_menus_and_window_title.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from main_window.main_window import MainWindow
from main_window.language import language_manager


def test_menu_titles_are_english():
    window = MainWindow()
    try:
        assert window.menus["file"].title() == "File"
        assert window.menus["edit"].title() == "Edit"
        assert window.menus["view"].title() == "View"
        assert window.menus["help"].title() == "Help"
    finally:
        window.close()


def test_window_title_is_english():
    window = MainWindow()
    try:
        assert window.windowTitle() == "Circuit Editor"
    finally:
        window.close()


def test_toolbar_title_is_english():
    window = MainWindow()
    try:
        assert window.toolbar.windowTitle() == "Tools"
    finally:
        window.close()


def test_retranslate_ui_reapplies_menu_and_window_titles():
    window = MainWindow()
    try:
        window.menus["file"].setTitle("stale")
        window.setWindowTitle("stale")
        window.toolbar.setWindowTitle("stale")

        window.retranslate_ui()

        assert window.menus["file"].title() == "File"
        assert window.windowTitle() == "Circuit Editor"
        assert window.toolbar.windowTitle() == "Tools"
    finally:
        window.close()


def test_retranslate_ui_preserves_filename_suffixed_title_when_file_open():
    """Regression test: retranslate_ui() used to unconditionally run
    self.setWindowTitle(self.tr("Circuit Editor")), clobbering the
    filename-suffixed title ("Circuit Editor – {filename}")
    SceneFileSession._update_window_title() sets whenever a file is open.
    Fixed by delegating to the file session's own title logic when a file
    is currently open, and only falling back to the bare title when none
    is."""
    window = MainWindow()
    try:
        window.file_session.current_file = "some/path/circuit.json"
        window.file_session._update_window_title()
        assert window.windowTitle() == "Circuit Editor – circuit.json"

        window.retranslate_ui()
        assert window.windowTitle() == "Circuit Editor – circuit.json"

        language_manager.apply_language(app, "pt_BR")
        try:
            window.retranslate_ui()
            assert window.windowTitle() == "Editor de Circuitos – circuit.json"
        finally:
            language_manager.apply_language(app, "en")
    finally:
        window.file_session.current_file = None
        window.close()
