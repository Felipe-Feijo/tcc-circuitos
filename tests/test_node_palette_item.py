# tests/test_node_palette_item.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from main_window.ui.palette.node_palette_item import NodePaletteItem

ICON_PATH = "resources/nodes/accumulator/accumulator.png"


def test_constructs_from_icon_path():
    item = NodePaletteItem("Accumulator", ICON_PATH)
    assert item.icon_path == ICON_PATH
    assert item.width() == 100  # small/default item_width from construction


def test_apply_size_updates_widths_and_font():
    item = NodePaletteItem("Accumulator", ICON_PATH)
    base_pt = item.text_label.font().pointSize()

    item.apply_size(pixmap_wh=(112, 76), item_width=160, font_delta=2)

    assert item.width() == 160
    assert item.text_label.font().pointSize() == base_pt + 2
    assert item.image_label.pixmap().width() <= 112
    assert item.image_label.pixmap().height() <= 76
