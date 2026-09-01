# tests/test_menus_and_window_title.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from main_window.main_window import MainWindow


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
