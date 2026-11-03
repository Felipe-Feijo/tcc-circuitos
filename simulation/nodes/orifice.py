"""Conductance validation shared by every node using the turbulent orifice
dP = copysign((Q / k)^2, Q): ThrottleValve, ThrottleCheckValve and the
hydraulic directional valves.

k = 0 is valid and means "fully blocked" -- each node then drops the
orifice from the solve instead of dividing by zero (a tiny k doesn't
work as a substitute: the system becomes ill-conditioned and the solver
stops converging). k < 0 has no physical meaning and is rejected.
"""

from __future__ import annotations


def parse_conductance(node, k) -> float:
    """Validates a conductance property and returns it as float.

    Raises:
        ValueError: k is missing (None) or negative.
    """
    if k is None:
        raise ValueError(
            f"{type(node).__name__} '{node.id}': required property 'k' is not set."
        )
    k = float(k)
    if k < 0:
        raise ValueError(
            f"{type(node).__name__} '{node.id}': property 'k' must be >= 0 "
            f"(0 = fully blocked), got {k}."
        )
    return k
