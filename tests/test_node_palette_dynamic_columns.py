# tests/test_node_palette_dynamic_columns.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from PyQt6.QtCore import Qt

from main_window.ui.palette.node_palette import NodePalette

ICON_PATH = "resources/nodes/accumulator/accumulator.png"


def test_recompute_columns_widens_on_more_space():
    palette = NodePalette()
    palette.show()  # Show widget to ensure layout is calculated
    section = palette.add_section("Hydraulic")
    section.add_node("Accumulator", ICON_PATH, callback=lambda: None)

    palette.resize(150, 400)
    app.processEvents()  # Let Qt process the resize and update viewport
    palette._recompute_columns()
    narrow_cols = section.num_columns

    palette.resize(600, 400)
    app.processEvents()  # Let Qt process the resize and update viewport
    palette._recompute_columns()
    wide_cols = section.num_columns

    assert wide_cols > narrow_cols


def test_recompute_columns_at_least_one():
    palette = NodePalette()
    palette.show()  # Show widget to ensure layout is calculated
    section = palette.add_section("Hydraulic")
    section.add_node("Accumulator", ICON_PATH, callback=lambda: None)

    palette.resize(1, 400)
    app.processEvents()  # Let Qt process the resize and update viewport
    palette._recompute_columns()

    assert section.num_columns >= 1
