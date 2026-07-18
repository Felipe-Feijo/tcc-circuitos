import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.check_valve.check_valve import CheckValve
from simulation.graph_builder import GraphBuilder
from simulation.nodes.check_valve.check_valve import CheckValve as CheckValveNode


def test_graph_builder_wires_default_anchors_x_and_y():
    node = CheckValve(domain="pneumatic")

    builder = GraphBuilder()
    domain_node = builder.add_node_from_item(node)

    assert isinstance(domain_node, CheckValveNode)
    assert set(domain_node.anchors.keys()) == {"X", "Y"}


def test_graph_builder_wires_piloted_anchors_x_y_and_z():
    node = CheckValve(domain="pneumatic")
    node.properties["piloted"] = True
    node.apply_properties()

    builder = GraphBuilder()
    domain_node = builder.add_node_from_item(node)

    assert isinstance(domain_node, CheckValveNode)
    assert set(domain_node.anchors.keys()) == {"X", "Y", "Z"}
