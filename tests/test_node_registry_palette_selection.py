# tests/test_node_registry_palette_selection.py
"""Clicking a palette item marks it selected (blue outline) while its node
is pending placement, and NodePalette.clear_selection() (already wired into
MainWindow.set_mode() on leaving ADD mode) turns it back off."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from main_window.ui.palette.node_palette import NodePalette
from main_window.ui.registry.node_registry import register_nodes


def test_clicking_palette_item_selects_it():
    palette = NodePalette()
    palette.add_section("Hydraulic")
    palette.add_section("Pneumatic")
    palette.add_section("Electric")
    register_nodes(palette, on_add_node=lambda node_desc: None)

    item = palette.sections["Hydraulic"]._items[0]
    assert item.selected is False

    item.mouseReleaseEvent(None)

    assert item.selected is True
    assert palette.selected_item is item


def test_clicking_another_item_deselects_the_previous_one():
    palette = NodePalette()
    palette.add_section("Hydraulic")
    palette.add_section("Pneumatic")
    palette.add_section("Electric")
    register_nodes(palette, on_add_node=lambda node_desc: None)

    first, second = palette.sections["Hydraulic"]._items[:2]
    first.mouseReleaseEvent(None)
    second.mouseReleaseEvent(None)

    assert first.selected is False
    assert second.selected is True


def test_clear_selection_turns_outline_off():
    palette = NodePalette()
    palette.add_section("Hydraulic")
    palette.add_section("Pneumatic")
    palette.add_section("Electric")
    register_nodes(palette, on_add_node=lambda node_desc: None)

    item = palette.sections["Hydraulic"]._items[0]
    item.mouseReleaseEvent(None)
    assert item.selected is True

    palette.clear_selection()

    assert item.selected is False
    assert palette.selected_item is None
