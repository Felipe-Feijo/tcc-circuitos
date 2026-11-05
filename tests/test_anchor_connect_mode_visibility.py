"""CONNECT mode anchor visibility: all anchors shown, colored by domain;
mid-connection, only anchors the source can connect to stay shown."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from PyQt6.QtWidgets import QApplication, QGraphicsScene
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor

app = QApplication.instance() or QApplication([])

from editor.editor_state import EditorState
from editor.mode import EditorMode
from graphics.anchors.anchor import AnchorItem
from graphics.items.base.nodes.node_item import NodeItem
from graphics.view import GraphicsView
from simulation.nodes.nodes import Junction

_ALL_DIRS = ["right", "left", "top", "bottom"]


class _TwoAnchorNode(NodeItem):
    node_type = "two_anchor_test_node"
    simulation_cls = Junction

    def setup(self) -> None:
        self.width = 0.0
        self.height = 0.0
        for name in ("A", "B"):
            self.add_anchor(AnchorItem(
                name, QPointF(0, 0), node=self, domain=self.domain,
                exit_directions={"external": list(_ALL_DIRS), "internal": list(_ALL_DIRS)},
            ))


class _Env:
    def __init__(self, light: bool = False):
        self.editor = EditorState()
        self.editor.is_light_theme = light
        self.scene = QGraphicsScene()
        self.view = GraphicsView(self.editor, self.scene)

    def node(self, domain: str) -> _TwoAnchorNode:
        node = _TwoAnchorNode(domain=domain)
        node.editor = self.editor
        self.scene.addItem(node)
        return node

    def set_mode(self, mode: EditorMode) -> None:
        # Same order as MainWindow.set_mode
        self.editor.mode = mode
        self.view.cleanup_temp_connection()

    def begin_connection(self, anchor: AnchorItem) -> None:
        # Same state changes as GraphicsView.handle_connect_press
        self.editor._connecting = True
        self.editor._conn_source_anchor = anchor
        self.view.start_temp_connection(anchor.node, anchor)


def _shown(anchor: AnchorItem) -> bool:
    return anchor.brush().color().alpha() > 0


def _rgb(anchor: AnchorItem) -> tuple[int, int, int]:
    color = anchor.brush().color()
    return color.red(), color.green(), color.blue()


def test_anchors_hidden_outside_connect_mode():
    env = _Env()
    node = env.node("pneumatic")
    env.set_mode(EditorMode.SELECT)
    assert not _shown(node.anchors["A"])


def test_all_anchors_shown_on_entering_connect_mode():
    env = _Env()
    pneumatic = env.node("pneumatic")
    electric = env.node("electric")
    env.set_mode(EditorMode.CONNECT)
    for anchor in (*pneumatic.anchors.values(), *electric.anchors.values()):
        assert _shown(anchor)


def test_anchors_hide_again_on_leaving_connect_mode():
    env = _Env()
    node = env.node("pneumatic")
    env.set_mode(EditorMode.CONNECT)
    env.set_mode(EditorMode.SELECT)
    assert not _shown(node.anchors["A"])


def test_node_added_during_connect_mode_shows_anchors():
    env = _Env()
    env.set_mode(EditorMode.CONNECT)
    node = env.node("hydraulic")
    assert _shown(node.anchors["A"])


@pytest.mark.parametrize("domain, light, expected", [
    ("pneumatic", False, (0, 255, 0)),
    ("pneumatic", True, (0, 128, 0)),
    ("electric", False, (255, 255, 0)),
    ("electric", True, (184, 132, 0)),
    ("hydraulic", False, (0, 255, 255)),
    ("hydraulic", True, (0, 137, 123)),
])
def test_anchor_color_by_domain_and_theme(domain, light, expected):
    env = _Env(light=light)
    node = env.node(domain)
    env.set_mode(EditorMode.CONNECT)
    assert _rgb(node.anchors["A"]) == expected


def test_theme_toggle_in_connect_mode_updates_color():
    env = _Env(light=False)
    node = env.node("electric")
    env.set_mode(EditorMode.CONNECT)
    node.on_theme_changed(True)
    assert _rgb(node.anchors["A"]) == (184, 132, 0)


def test_other_domain_hidden_during_connection():
    env = _Env()
    source = env.node("pneumatic")
    other = env.node("electric")
    env.set_mode(EditorMode.CONNECT)
    env.begin_connection(source.anchors["A"])
    assert not _shown(other.anchors["A"])


def test_same_domain_on_other_node_stays_shown_during_connection():
    env = _Env()
    source = env.node("pneumatic")
    target = env.node("pneumatic")
    env.set_mode(EditorMode.CONNECT)
    env.begin_connection(source.anchors["A"])
    assert _rgb(target.anchors["A"]) == (0, 255, 0)


def test_source_node_other_anchors_hidden_during_connection():
    # GraphicsView._complete_connect_press refuses same-node connections.
    env = _Env()
    source = env.node("pneumatic")
    env.set_mode(EditorMode.CONNECT)
    env.begin_connection(source.anchors["A"])
    assert not _shown(source.anchors["B"])


def test_source_anchor_stays_gray_during_connection():
    env = _Env()
    source = env.node("pneumatic")
    env.set_mode(EditorMode.CONNECT)
    env.begin_connection(source.anchors["A"])
    assert source.anchors["A"].brush().color() == QColor(Qt.GlobalColor.gray)


def test_hidden_anchor_stops_accepting_hover():
    # An invisible anchor on top must not swallow hover from a connectable
    # one beneath it: Qt only delivers hover to the topmost accepting item.
    env = _Env()
    source = env.node("pneumatic")
    other = env.node("electric")
    env.set_mode(EditorMode.CONNECT)
    env.begin_connection(source.anchors["A"])
    assert not other.anchors["A"].acceptHoverEvents()


def test_anchors_return_when_connection_is_cancelled():
    env = _Env()
    source = env.node("pneumatic")
    other = env.node("electric")
    env.set_mode(EditorMode.CONNECT)
    env.begin_connection(source.anchors["A"])
    env.view.cleanup_temp_connection()
    assert _rgb(other.anchors["A"]) == (255, 255, 0)
    assert other.anchors["A"].acceptHoverEvents()
    assert _rgb(source.anchors["B"]) == (0, 255, 0)
    assert _rgb(source.anchors["A"]) == (0, 255, 0)


def test_hover_shows_highlight_and_leave_restores_domain_color():
    env = _Env()
    node = env.node("pneumatic")
    anchor = node.anchors["A"]
    env.set_mode(EditorMode.CONNECT)
    anchor.hoverEnterEvent(None)
    assert env.editor.hover_anchor is anchor
    assert anchor.brush().color() == QColor(Qt.GlobalColor.red)
    anchor.hoverLeaveEvent(None)
    assert env.editor.hover_anchor is None
    assert _rgb(anchor) == (0, 255, 0)


def test_junction_dot_of_other_domain_stays_gray_during_connection():
    # A 3+ connection dot is part of the drawn circuit, not a connect target.
    env = _Env()
    source = env.node("pneumatic")
    other = env.node("electric")
    anchor = other.anchors["A"]
    anchor.always_visible = True
    env.set_mode(EditorMode.CONNECT)
    env.begin_connection(source.anchors["A"])
    assert anchor.brush().color() == QColor(Qt.GlobalColor.lightGray)
    assert not anchor.acceptHoverEvents()
