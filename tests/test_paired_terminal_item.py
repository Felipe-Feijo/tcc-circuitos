"""PairedTerminalItem spawns its far end + the connecting rail the first
time it's added to a real scene -- and only then: not for an ADD-mode
preview ghost, not when reconstructed via from_dict, and only once even
if the node is removed and re-added to a scene."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene
from PyQt6.QtCore import QPointF

app = QApplication.instance() or QApplication([])

from graphics.anchors.anchor import AnchorItem
from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.paired_terminal_item import PairedTerminalItem
from simulation.nodes.nodes import Junction


class _FarEnd(NodeItem):
    node_type = "dummy_far_end"
    simulation_cls = Junction

    def setup(self) -> None:
        self.width = 0.0
        self.height = 0.0
        self.add_anchor(AnchorItem(
            "X1", QPointF(0, 0), node=self, domain=self.domain,
            exit_directions={"external": ["right", "left", "top", "bottom"]},
        ))


class _DummyPaired(PairedTerminalItem):
    node_type = "dummy_paired"
    simulation_cls = Junction

    def initialize_own_anchor(self) -> None:
        self.width = 40.0
        self.height = 20.0
        self.add_anchor(AnchorItem(
            "X1", QPointF(20, 20), node=self, domain=self.domain,
            exit_directions={"external": ["right", "left", "top", "bottom"]},
        ))

    def create_far_end(self):
        return _FarEnd(domain=self.domain)


def test_spawns_far_end_and_rail_on_real_scene_add():
    scene = QGraphicsScene()
    item = _DummyPaired(domain="electric")
    scene.addItem(item)

    far_ends = [i for i in scene.items() if isinstance(i, _FarEnd)]
    conns = [i for i in scene.items() if isinstance(i, ConnectionItem)]

    assert len(far_ends) == 1
    assert len(conns) == 1
    assert {conns[0].source, conns[0].target} == {item, far_ends[0]}


def test_far_end_is_offset_horizontally_by_pair_offset_x():
    scene = QGraphicsScene()
    item = _DummyPaired(domain="electric")
    item.setPos(100, 200)
    scene.addItem(item)

    far_end = next(i for i in scene.items() if isinstance(i, _FarEnd))
    own_anchor = item.anchors["X1"]
    far_anchor = far_end.anchors["X1"]

    assert far_anchor.scenePos().x() == own_anchor.scenePos().x() + _DummyPaired.PAIR_OFFSET_X
    assert far_anchor.scenePos().y() == own_anchor.scenePos().y()


def test_preview_does_not_spawn_pair():
    scene = QGraphicsScene()
    item = _DummyPaired(domain="electric")
    item.apply_preview_constraints()
    scene.addItem(item)

    assert not any(isinstance(i, _FarEnd) for i in scene.items())


def test_loading_reconstruction_does_not_spawn_pair():
    scene = QGraphicsScene()
    item = _DummyPaired(domain="electric", _loading=True)
    scene.addItem(item)

    assert not any(isinstance(i, _FarEnd) for i in scene.items())


def test_pair_spawns_only_once_across_remove_and_readd():
    scene = QGraphicsScene()
    item = _DummyPaired(domain="electric")
    scene.addItem(item)
    scene.removeItem(item)
    scene.addItem(item)

    conns = [i for i in scene.items() if isinstance(i, ConnectionItem)]
    assert len(conns) == 1
