# tests/test_node_palette_dock.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QMainWindow
app = QApplication.instance() or QApplication([])

from PyQt6.QtCore import QSettings
from main_window.ui.docks.node_palette_dock import create_node_palette
from main_window import settings


def _ini_settings(tmp_path, monkeypatch):
    s = QSettings(str(tmp_path / "test_settings.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(settings, "_default_settings", lambda: s)
    return s


def test_dock_is_not_fixed_width_and_has_bounds():
    main_window = QMainWindow()
    main_window.set_mode = lambda *a, **kw: None
    palette, dock = create_node_palette(main_window)

    assert dock.minimumWidth() == 180
    assert dock.maximumWidth() == 700


def test_dock_applies_persisted_tier_on_startup(tmp_path, monkeypatch):
    _ini_settings(tmp_path, monkeypatch)
    settings.set_palette_tier("large")

    main_window = QMainWindow()
    main_window.set_mode = lambda *a, **kw: None
    palette, dock = create_node_palette(main_window)

    assert palette.current_tier == "large"

    # Prove the item-level resizing wiring actually ran (the second
    # set_size_tier call after register_nodes), not just that
    # palette.current_tier happens to match what NodePalette.__init__
    # already reads from settings on its own.
    section = next(s for s in palette.sections.values() if s._items)
    item = section._items[0]
    assert item.width() == palette.SIZE_TIERS["large"]["item_width"]
    assert item.width() == 160
