"""JunctionNodeItem: nó gráfico quase invisível (sem corpo), 1 anchor só,
usado como ponto de derivação no meio de um fio. Deve funcionar com o
class_registry genérico de NodeItem (save/load) sem nenhum código extra."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.junction_node_item import JunctionNodeItem
from simulation.nodes.nodes import Junction


def test_junction_node_item_has_one_anchor_with_all_exit_directions():
    item = JunctionNodeItem(domain="electric")

    assert list(item.anchors.keys()) == ["J"]
    anchor = item.anchors["J"]
    assert set(anchor.exit_directions["external"]) == {"right", "left", "top", "bottom"}
    assert set(anchor.exit_directions["internal"]) == {"right", "left", "top", "bottom"}
    assert item.node_type == "junction"
    assert item.simulation_cls is Junction
    assert item.palette_meta() is None


def test_junction_node_item_registered_in_class_registry():
    assert NodeItem.class_registry["JunctionNodeItem"] is JunctionNodeItem


def test_junction_node_item_to_dict_from_dict_round_trip():
    item = JunctionNodeItem(domain="electric")
    item.setPos(12.0, -34.0)

    data = item.to_dict()
    assert data["type"] == "JunctionNodeItem"

    restored = JunctionNodeItem.from_dict(data)
    assert restored.pos().x() == 12.0
    assert restored.pos().y() == -34.0
    assert list(restored.anchors.keys()) == ["J"]
