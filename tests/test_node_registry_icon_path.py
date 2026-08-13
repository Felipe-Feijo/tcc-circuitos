# tests/test_node_registry_icon_path.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from main_window.ui.palette.node_palette import NodePalette
from main_window.ui.registry.node_registry import register_nodes


def test_register_nodes_gives_items_a_real_icon_path():
    palette = NodePalette()
    palette.add_section("Hydraulic")
    palette.add_section("Pneumatic")
    palette.add_section("Electric")

    register_nodes(palette, on_add_node=lambda node_desc: None)

    hydraulic_items = palette.sections["Hydraulic"]._items
    assert len(hydraulic_items) > 0
    for item in hydraulic_items:
        assert item.icon_path.endswith(".png")
        assert Path(item.icon_path).exists()
