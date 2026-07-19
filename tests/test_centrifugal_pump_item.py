import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.pumps.centrifugal_pump import CentrifugalPump
from simulation.nodes.pumps.centrifugal_pump import CentrifugalPump as CentrifugalPumpNode


def test_palette_meta():
    meta = CentrifugalPump.palette_meta()
    assert meta.domains == ("hydraulic",)
    assert meta.name == "Centrifugal Pump"


def test_simulation_cls_linkage():
    assert CentrifugalPump.simulation_cls is CentrifugalPumpNode


def test_anchors_match_fixed_displacement_pump_layout():
    node = CentrifugalPump(domain="hydraulic")
    assert set(node.anchors.keys()) == {"P", "S"}
    assert node.anchors["P"].pos().y() == 0
    assert node.anchors["S"].pos().y() == node.height
    assert node.anchors["P"].pos().x() == node.anchors["S"].pos().x()


def test_properties_dialog_requires_h_and_qmax_only_for_hydraulic():
    node = CentrifugalPump(domain="hydraulic")
    dialog = node.build_properties_dialog()
    assert dialog._field_h is not None
    assert dialog._field_qmax is not None
