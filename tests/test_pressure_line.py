import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.nodes.pressure_line import PressureLine
from simulation.connections import Connection


def make_pressure_line(n_anchors: int) -> PressureLine:
    pl = PressureLine("pl1", domain="pneumatic")
    for i in range(1, n_anchors + 1):
        pl.add_anchor(f"X{i}", domain="pneumatic")
    return pl


def test_no_real_connections_chains_only_endpoints():
    pl = make_pressure_line(6)
    assert pl.get_internal_connections() == [("X1", "X6")]


def test_real_connections_split_the_chain():
    pl = make_pressure_line(6)
    other = PressureLine("pl2", domain="pneumatic")
    other.add_anchor("Y1", domain="pneumatic")

    Connection(pl.get_anchor("X3"), other.get_anchor("Y1"))

    assert pl.get_internal_connections() == [("X1", "X3"), ("X3", "X6")]


def test_two_anchors_returns_single_pair():
    pl = make_pressure_line(2)
    assert pl.get_internal_connections() == [("X1", "X2")]


def test_single_anchor_returns_empty():
    pl = make_pressure_line(1)
    assert pl.get_internal_connections() == []
