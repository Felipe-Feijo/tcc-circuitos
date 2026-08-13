# tests/test_palette_section.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from main_window.ui.palette.palette_section import PaletteSection

ICON_PATH = "resources/nodes/accumulator/accumulator.png"


def test_add_node_uses_icon_path_and_tracks_item():
    section = PaletteSection("Hydraulic", num_columns=2)
    calls = []
    item = section.add_node("Accumulator", ICON_PATH, callback=lambda: calls.append(1))

    assert item.icon_path == ICON_PATH
    assert item in section._items
    item.mouseReleaseEvent(None)
    assert calls == [1]


def test_set_num_columns_relayouts_without_recreating_items():
    section = PaletteSection("Hydraulic", num_columns=2)
    items = [section.add_node(f"Node{i}", ICON_PATH, callback=lambda: None) for i in range(5)]

    section.set_num_columns(3)

    assert section.num_columns == 3
    # same widget instances, just repositioned
    assert section._items == items
    idx = section.grid_layout.indexOf(items[3])
    row, col, _, _ = section.grid_layout.getItemPosition(idx)
    assert (row, col) == (1, 0)  # item 3 -> row 3//3=1, col 3%3=0


def test_set_num_columns_noop_when_unchanged():
    section = PaletteSection("Hydraulic", num_columns=2)
    section.add_node("Node0", ICON_PATH, callback=lambda: None)
    layout_before = section.grid_layout

    section.set_num_columns(2)

    assert section.grid_layout is layout_before  # nothing rebuilt


def test_apply_item_size_resizes_all_items():
    section = PaletteSection("Hydraulic", num_columns=2)
    item = section.add_node("Accumulator", ICON_PATH, callback=lambda: None)

    section.apply_item_size(pixmap_wh=(112, 76), item_width=160, font_delta=2)

    assert item.width() == 160
