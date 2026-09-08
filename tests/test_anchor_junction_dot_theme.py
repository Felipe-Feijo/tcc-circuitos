"""The junction dot's outline was hardcoded white (AnchorItem.
refresh_junction_dot), never consulting the node's theme -- invisible
against a light-theme white/near-white canvas (reported: "a outline
das junctions deveria ficar preta no light mode"). Same class of bug as
connection_item.py's state colors and the default connection pen: read
self.node.use_light_theme, same white-on-dark/black-on-light
convention already used there.

Also: NodeItem.on_theme_changed() propagated the new theme to labels
but never re-applied each anchor's junction-dot pen, so an
already-visible dot stayed the OLD color until the next connection
create/delete -- refresh_junction_dot() needed a call there too.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene
from PyQt6.QtCore import Qt

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.junction_node_item import JunctionNodeItem


def _three_way_junction(use_light_theme: bool) -> JunctionNodeItem:
    item = JunctionNodeItem(domain="electric")
    item.use_light_theme = use_light_theme
    anchor = item.anchors["J"]

    class _FakeConn:
        def __init__(self, a, b):
            self.source_anchor, self.target_anchor = a, b

    item.connections = [_FakeConn(anchor, "x"), _FakeConn("y", anchor), _FakeConn(anchor, "z")]
    anchor.refresh_junction_dot()
    return item


def test_junction_dot_outline_is_black_in_light_theme():
    item = _three_way_junction(use_light_theme=True)
    assert item.anchors["J"].pen().color() == Qt.GlobalColor.black


def test_junction_dot_outline_is_white_in_dark_theme():
    item = _three_way_junction(use_light_theme=False)
    assert item.anchors["J"].pen().color() == Qt.GlobalColor.white


def test_on_theme_changed_updates_an_already_visible_dot():
    """The dot's pen must update live on toggle, not just next time a
    connection is created/removed."""
    item = _three_way_junction(use_light_theme=False)
    anchor = item.anchors["J"]
    assert anchor.pen().color() == Qt.GlobalColor.white

    item.on_theme_changed(True)

    assert anchor.pen().color() == Qt.GlobalColor.black
