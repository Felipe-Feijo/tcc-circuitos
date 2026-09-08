"""DoubleActingCylinder.equations()'s conservation equation enforced
Q_a + Q_b = 0 (equal-and-opposite flow) regardless of the two chambers'
areas -- but a double-acting cylinder's rod makes area_b strictly less
than area_a (area_b = area_a - rod cross-section, and rod_diameter is a
required property, so this is never zero). For an incompressible fluid,
volume conservation per chamber gives Q_a/area_a = -Q_b/area_b (same
piston velocity on both sides, different swept volume), i.e.
area_b*Q_a + area_a*Q_b = 0 -- not Q_a + Q_b = 0.

Verified against a real circuit (tests/fixtures/simple_hidr.json,
bore=0.05 rod_diameter=0.015 -> area_b/area_a=0.91): velocity computed
from side A (Q_a/area_a) disagreed with velocity computed from side B
(-Q_b/area_b) by ~10%, matching the area ratio exactly -- port B's
reported flow (whatever downstream component is wired there) was
~10% too large in magnitude, a real physics error baked into the
model, not caught by system-level flow-balance checks (the rest of the
circuit solves consistently around whatever Q_b the cylinder emits).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

from simulation.nodes.cylinder.double_acting_cylinder import DoubleActingCylinder


def _cylinder_mid_stroke():
    cyl = DoubleActingCylinder(
        "c1", domain="hydraulic",
        properties={"bore": 0.05, "rod_diameter": 0.015, "stroke": 0.5},
    )
    cyl.add_anchor("A", domain="hydraulic")
    cyl.add_anchor("B", domain="hydraulic")
    cyl.anchors["A"].pressure_var = "P_A"
    cyl.anchors["B"].pressure_var = "P_B"
    cyl.x = 0.25  # mid-stroke -- away from either end-stop's special-cased branch
    return cyl


def _idx(cyl):
    return {
        cyl.flow_var_a: 0, cyl.flow_var_b: 1,
        "P_A": 2, "P_B": 3,
    }


def test_conservation_equation_is_satisfied_by_the_area_weighted_root():
    cyl = _cylinder_mid_stroke()
    idx = _idx(cyl)

    Q_a = 1e-4
    Q_b_physically_correct = -Q_a * (cyl.area_b / cyl.area_a)
    x = np.array([Q_a, Q_b_physically_correct, 0.0, 0.0])

    _, eq_conservation = cyl.equations(x, idx)

    assert abs(eq_conservation) < 1e-12


def test_conservation_equation_rejects_equal_and_opposite_flow():
    """The OLD (buggy) root Q_a = -Q_b must now read as a real
    violation, not a solution -- area_a != area_b for any valid
    double-acting cylinder (rod_diameter is required and > 0)."""
    cyl = _cylinder_mid_stroke()
    idx = _idx(cyl)

    Q_a = 1e-4
    x = np.array([Q_a, -Q_a, 0.0, 0.0])

    _, eq_conservation = cyl.equations(x, idx)

    # Scale of the violation should track the area mismatch, not be
    # numerical noise.
    expected_magnitude = Q_a * abs(1 - cyl.area_b / cyl.area_a)
    assert abs(eq_conservation - expected_magnitude) < 1e-15 or \
        abs(eq_conservation + expected_magnitude) < 1e-15
