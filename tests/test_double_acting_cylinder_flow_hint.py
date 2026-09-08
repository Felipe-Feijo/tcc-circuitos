"""Regression: DoubleActingCylinder.flow_hint used self.friction (a
hidden, artificially tiny regularization constant -- see __init__'s
comment, "minimum value to close the equation", never a real physical
value) to estimate a characteristic flow from external_force. Since
friction=1e-3, even a small external_force blows this up to several
orders of magnitude above any real circuit flow (e.g. external_force=1N
-> ~1.96 m3/s, vs a typical pump flow of ~1.57e-4 m3/s).

ScaleManager._estimate_flow() takes the MAX flow_hint across every
hydraulic node with no priority given to the pump's (correct) hint --
so this one bogus value became the whole circuit's q_ref, corrupting
the solver's flow-variable scaling and residual-acceptance threshold
enough to silently accept a solution that doesn't conserve flow at the
cylinder's ports. Reproduced with a real circuit (pump -> valve ->
double-acting cylinder with external_force=1.0, relief p_set=4e5):
flow imbalance ~1.3e-4 m3/s at both cylinder ports, persisting across
many simulation steps -- confirmed absent with external_force=0.0.

initial_guess() already computes its own, better estimate straight
from the pressure balance (P_a, P_b, external_force, friction) and
does not call flow_hint at all -- flow_hint has no correct remaining
purpose, so it's removed, falling back to HydraulicMixin's safe
default (0.0), same as SingleActingCylinder (which never overrode it).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.nodes.cylinder.double_acting_cylinder import DoubleActingCylinder


def _cylinder(external_force):
    return DoubleActingCylinder(
        "c1", domain="hydraulic",
        properties={
            "bore": 0.05, "rod_diameter": 0.015, "stroke": 0.5,
            "external_force": external_force,
        },
    )


def test_flow_hint_ignores_external_force():
    cyl = _cylinder(external_force=1.0)
    assert cyl.flow_hint == 0.0


def test_flow_hint_is_zero_regardless_of_external_force_sign():
    assert _cylinder(external_force=-50.0).flow_hint == 0.0
    assert _cylinder(external_force=0.0).flow_hint == 0.0
