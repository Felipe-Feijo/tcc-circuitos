# tests/test_accumulator_item.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.accumulator import Accumulator
from simulation.nodes.accumulator import Accumulator as AccumulatorNode


def test_palette_meta():
    meta = Accumulator.palette_meta()
    assert meta.domains == ("hydraulic",)
    assert meta.name == "Accumulator"
    assert meta.sprite == "resources/nodes/accumulator/accumulator.png"


def test_simulation_cls_linkage():
    assert Accumulator.simulation_cls is AccumulatorNode


def test_single_port_anchor():
    node = Accumulator(domain="hydraulic")
    assert set(node.anchors.keys()) == {"P"}
    assert node.anchors["P"].pos().x() == 42
    assert node.anchors["P"].pos().y() == 194


def test_body_dimensions_match_sprite():
    node = Accumulator(domain="hydraulic")
    assert node.width == 85
    assert node.height == 195


def test_properties_dialog_requires_v0_and_p0():
    node = Accumulator(domain="hydraulic")
    dialog = node.build_properties_dialog()
    assert dialog._field_v0 is not None
    assert dialog._field_p0 is not None


def test_level_marker_y_at_empty():
    node = Accumulator(domain="hydraulic")
    node._level = 0.0
    assert node._level_marker_y() == 124 - 18  # fundo da parede reta (vazio) menos a linha do marcador


def test_level_marker_y_at_full():
    node = Accumulator(domain="hydraulic")
    node._level = 1.0
    assert node._level_marker_y() == 39 - 18  # topo da parede reta (cheio) menos a linha do marcador


def test_level_marker_y_at_half():
    node = Accumulator(domain="hydraulic")
    node._level = 0.5
    assert node._level_marker_y() == (39 + 124) / 2 - 18


def test_update_from_domain_sets_level():
    node = Accumulator(domain="hydraulic")
    domain_node = AccumulatorNode("acc", domain="hydraulic", properties={"V0": 1e-3, "P0": 3e6})
    domain_node.add_anchor("P", domain="hydraulic")
    domain_node.Vf = 0.5e-3

    node.update_from_domain(domain_node)
    assert node._level == 0.5


def test_reset_visual_state_zeroes_level():
    node = Accumulator(domain="hydraulic")
    node._level = 0.7
    node.reset_visual_state()
    assert node._level == 0.0
