import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from simulation.connections import Connection
from simulation.nodes.directional_valve.valve_2_2_ways import Valve_2_2_Ways
from simulation.nodes.pilot_operated_relief_valve import PilotOperatedReliefValve
from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
from simulation.nodes.relief_valve import ReliefValve
from simulation.nodes.reservoir import Reservoir
from simulation.nodes.throttle_valve import ThrottleValve
from simulation.simulation_engine import SimulationEngine

P_SET = 1.0e7
P_VENT = 3.0e5
Q = 1e-3


def _node(cls, nid, anchors, **props):
    n = cls(nid, domain="hydraulic", properties=props)
    for a in anchors:
        n.add_anchor(a, domain="hydraulic")
    return n


class Circuit:
    """Fixed-displacement pump -> valve under test -> tank."""

    def __init__(self, q=Q):
        self.nodes = {}
        self.conns = []
        self.pump = self.add(FixedDisplacementPump, "pump", "PS", Q=q)
        self.connect(self.pump, "S", self.add(Reservoir, "res_s", "T", pressure=0.0), "T")
        self.tank = self.add(Reservoir, "tank", "T", pressure=0.0)

    def add(self, cls, nid, anchors, **props):
        n = _node(cls, nid, anchors, **props)
        self.nodes[nid] = n
        return n

    def connect(self, a, an, b, bn):
        self.conns.append(Connection(a.get_anchor(an), b.get_anchor(bn)))

    def run(self):
        engine = SimulationEngine(self.nodes, {c.id: c for c in self.conns})
        engine.run_until_stable(dt=1.0)
        return engine

    def p_pump(self):
        return self.pump.get_anchor("P").pressure


def with_valve(q=Q, p_set=P_SET, p_vent=P_VENT):
    c = Circuit(q)
    v = c.add(PilotOperatedReliefValve, "po", "PTX", p_set=p_set, p_vent=p_vent)
    c.connect(c.pump, "P", v, "P")
    c.connect(v, "T", c.tank, "T")
    return c, v


def add_remote_relief(c, v, p_r):
    rem = c.add(ReliefValve, "remote", "PT", p_set=p_r)
    c.connect(v, "X", rem, "P")
    c.connect(rem, "T", c.add(Reservoir, "tank_r", "T", pressure=0.0), "T")


# 1. X free

def test_x_free_regulates_at_p_set_plus_p_vent():
    c, v = with_valve()
    c.run()
    assert c.p_pump() == pytest.approx(P_SET + P_VENT, rel=1e-3)
    assert v.get_anchor("X").flow == pytest.approx(0.0, abs=1e-9)
    assert v.get_anchor("T").flow == pytest.approx(-Q, rel=1e-3)


def test_x_free_matches_direct_relief_and_discrete_build():
    c, _ = with_valve()
    c.run()
    p_component = c.p_pump()

    d = Circuit()
    rv = d.add(ReliefValve, "rv", "PT", p_set=P_SET + P_VENT)
    d.connect(d.pump, "P", rv, "P")
    d.connect(rv, "T", d.tank, "T")
    d.run()

    m = Circuit()
    orif = m.add(ThrottleValve, "orif", "XY", k=PilotOperatedReliefValve.K_ORIFICE)
    main = m.add(ReliefValve, "main", "PTY", p_set=P_VENT, piloted=True)
    pilot = m.add(ReliefValve, "pilot", "PT", p_set=P_SET)
    m.connect(m.pump, "P", main, "P")
    m.connect(m.pump, "P", orif, "X")
    m.connect(orif, "Y", main, "Y")
    m.connect(orif, "Y", pilot, "P")
    m.connect(main, "T", m.tank, "T")
    m.connect(pilot, "T", m.tank, "T")
    m.run()

    assert p_component == pytest.approx(d.p_pump(), rel=1e-3)
    assert p_component == pytest.approx(m.p_pump(), rel=1e-3)


# 2. X to tank

def test_x_to_tank_regulates_at_p_vent():
    c, v = with_valve()
    c.connect(v, "X", c.add(Reservoir, "tank_x", "T", pressure=0.0), "T")
    c.run()
    assert c.p_pump() == pytest.approx(P_VENT, rel=1e-3)
    assert v.get_anchor("X").flow < 0  # pilot flow leaves through X


# 3. / 4. remote relief

def test_remote_relief_below_p_set_regulates_at_p_r_plus_p_vent():
    c, v = with_valve()
    add_remote_relief(c, v, 5.0e6)
    c.run()
    assert c.p_pump() == pytest.approx(5.0e6 + P_VENT, rel=1e-3)


def test_remote_relief_above_p_set_internal_pilot_wins():
    c, v = with_valve()
    add_remote_relief(c, v, 1.5e7)
    c.run()
    assert c.p_pump() == pytest.approx(P_SET + P_VENT, rel=1e-3)


# 5. vent through a 2/2 switched mid-simulation

def test_vent_valve_switched_mid_simulation():
    c, v = with_valve()
    vent = c.add(Valve_2_2_Ways, "vent", "PA", k=1e-5)
    vent.body_state = 0  # blocked
    c.connect(v, "X", vent, "P")
    c.connect(vent, "A", c.add(Reservoir, "tank_x", "T", pressure=0.0), "T")
    engine = SimulationEngine(c.nodes, {cn.id: cn for cn in c.conns})

    engine.run_until_stable(dt=1.0)
    assert c.p_pump() == pytest.approx(P_SET + P_VENT, rel=1e-3)

    vent.body_state = 1
    engine.run_until_stable(dt=1.0)
    assert c.p_pump() == pytest.approx(P_VENT, rel=1e-2)

    vent.body_state = 0
    engine.run_until_stable(dt=1.0)
    assert c.p_pump() == pytest.approx(P_SET + P_VENT, rel=1e-3)


# Review focus 1: pilot-only regime

def test_small_pump_flow_pilot_only_regime():
    q = 0.5 * PilotOperatedReliefValve.K_ORIFICE * P_VENT ** 0.5
    c, _ = with_valve(q=q)
    c.run()
    expected = P_SET + (q / PilotOperatedReliefValve.K_ORIFICE) ** 2
    assert c.p_pump() == pytest.approx(expected, rel=1e-3)
    assert P_SET < c.p_pump() < P_SET + P_VENT
