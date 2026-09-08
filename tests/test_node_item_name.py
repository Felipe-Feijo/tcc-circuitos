"""NodeItem.name: a free-text display name, separate from the UUID `id`,
used to identify a node in report charts and the properties dialog
instead of the raw id."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.junction_node_item import JunctionNodeItem


def test_fresh_node_has_empty_name():
    item = JunctionNodeItem(domain="electric")
    assert item.name == ""


def test_to_dict_includes_name():
    item = JunctionNodeItem(domain="electric")
    item.name = "Cilindro A"
    assert item.to_dict()["name"] == "Cilindro A"


def test_from_dict_restores_name():
    item = JunctionNodeItem(domain="electric")
    item.name = "Cilindro A"
    data = item.to_dict()

    restored = JunctionNodeItem.from_dict(data)
    assert restored.name == "Cilindro A"


def test_from_dict_defaults_missing_name_to_empty_string():
    """Files saved before this feature existed have no "name" key."""
    item = JunctionNodeItem(domain="electric")
    data = item.to_dict()
    del data["name"]

    restored = JunctionNodeItem.from_dict(data)
    assert restored.name == ""
