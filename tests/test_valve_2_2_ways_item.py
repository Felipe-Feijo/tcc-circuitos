import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.directional_valve.valve_2_2_ways import Valve_2_2_Ways
from simulation.nodes.directional_valve.valve_2_2_ways import Valve_2_2_Ways as Valve_2_2_WaysNode


def test_palette_meta_includes_both_domains():
    meta = Valve_2_2_Ways.palette_meta()
    assert meta.domains == ("pneumatic", "hydraulic")
    assert meta.name == "Valve 2/2 Ways"


def test_simulation_cls_linkage():
    assert Valve_2_2_Ways.simulation_cls is Valve_2_2_WaysNode


def test_anchors_p_and_a_share_the_same_x_at_rest():
    node = Valve_2_2_Ways(domain="pneumatic")
    assert set(node.anchors.keys()) == {"A", "P"}
    a_x = node.anchors["A"].pos().x()
    p_x = node.anchors["P"].pos().x()
    assert abs(a_x - p_x) < 1e-6  # mesma coordenada X -- uma porta só, topo/base
    assert node.anchors["A"].pos().y() == 0
    assert node.anchors["P"].pos().y() == node.height


def test_body_visuals_offset_matches_147px_commutation_shift():
    node = Valve_2_2_Ways(domain="pneumatic")
    assert node.BODY_VISUALS[0]["offset"].x() == 0
    assert node.BODY_VISUALS[1]["offset"].x() == 147
