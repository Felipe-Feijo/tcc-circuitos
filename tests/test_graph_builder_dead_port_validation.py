"""Pre-flight validation: a sensing-only port left unconnected (e.g. a
piloted valve's 'Y' line) must be caught by raise_if_errors() -- the same
mechanism that already blocks simulation start for a missing required
property -- instead of surfacing as an exception mid-solve."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.relief_valve import ReliefValve
from graphics.items.base.nodes.pressure_reducing_valve import PressureReducingValve
from graphics.items.base.nodes.reservoir import Reservoir
from graphics.items.base.connections.connection_item import ConnectionItem
from simulation.graph_builder import GraphBuilder


def test_piloted_relief_valve_with_unconnected_y_raises_on_raise_if_errors():
    relief = ReliefValve(domain="hydraulic")
    relief.properties["p_set"] = 1.5e7
    relief.properties["piloted"] = True
    relief.apply_properties()

    builder = GraphBuilder()
    builder.add_node_from_item(relief)

    with pytest.raises(ValueError, match="Y"):
        builder.raise_if_errors()


def test_piloted_relief_valve_with_connected_y_does_not_raise():
    relief = ReliefValve(domain="hydraulic")
    relief.properties["p_set"] = 1.5e7
    relief.properties["piloted"] = True
    relief.apply_properties()
    source = Reservoir(domain="hydraulic")
    conn = ConnectionItem(relief, relief.anchors["Y"], source, source.anchors["T"])

    builder = GraphBuilder()
    builder.add_node_from_item(relief)
    builder.add_node_from_item(source)
    builder.add_connection_from_item(conn)

    builder.raise_if_errors()  # must not raise


def test_piloted_pressure_reducing_valve_with_unconnected_y_raises_on_raise_if_errors():
    prv = PressureReducingValve(domain="hydraulic")
    prv.properties["p_set"] = 1.5e7
    prv.properties["piloted"] = True
    prv.apply_properties()

    builder = GraphBuilder()
    builder.add_node_from_item(prv)

    with pytest.raises(ValueError, match="Y"):
        builder.raise_if_errors()


def test_piloted_pressure_reducing_valve_with_connected_y_does_not_raise():
    prv = PressureReducingValve(domain="hydraulic")
    prv.properties["p_set"] = 1.5e7
    prv.properties["piloted"] = True
    prv.apply_properties()
    source = Reservoir(domain="hydraulic")
    conn = ConnectionItem(prv, prv.anchors["Y"], source, source.anchors["T"])

    builder = GraphBuilder()
    builder.add_node_from_item(prv)
    builder.add_node_from_item(source)
    builder.add_connection_from_item(conn)

    builder.raise_if_errors()  # must not raise


def test_non_piloted_valves_are_unaffected_by_dead_port_validation():
    relief = ReliefValve(domain="hydraulic")
    relief.properties["p_set"] = 1.5e7
    prv = PressureReducingValve(domain="hydraulic")
    prv.properties["p_set"] = 1.5e7

    builder = GraphBuilder()
    builder.add_node_from_item(relief)
    builder.add_node_from_item(prv)

    builder.raise_if_errors()  # neither has piloted=True -- no Y port to check
