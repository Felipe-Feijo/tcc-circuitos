"""NodeItem._loading distinguishes a freshly-constructed instance (palette
add, ADD-mode preview) from one reconstructed by from_dict (file load,
undo/redo restore, clipboard paste) -- PairedTerminalItem (Task 2) uses
this to spawn its pair only on the former."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.junction_node_item import JunctionNodeItem


def test_fresh_node_is_not_loading():
    item = JunctionNodeItem(domain="electric")
    assert item._loading is False


def test_from_dict_reconstructed_node_is_loading():
    item = JunctionNodeItem(domain="electric")
    data = item.to_dict()

    restored = JunctionNodeItem.from_dict(data)
    assert restored._loading is True
