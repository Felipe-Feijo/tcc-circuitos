"""Conductance validation shared by every node using the turbulent orifice
dP = copysign((Q / k)^2, Q): ThrottleValve, ThrottleCheckValve and the
hydraulic directional valves.

k = 0 is valid and means "fully blocked" -- each node then drops the
orifice from the solve instead of dividing by zero (a tiny k doesn't
work as a substitute: the system becomes ill-conditioned and the solver
stops converging). k < 0 has no physical meaning and is rejected.
"""

from __future__ import annotations
from simulation.nodes.param_checks import ParamError


def parse_conductance(node, k) -> float:
    """Validates a conductance property and returns it as float.

    Raises:
        ValueError: k is missing (None) or negative.
    """
    if k is None:
        raise ParamError(node, "missing_property", key="k")
    k = float(k)
    check_conductance(node, k)
    return k


def check_conductance(node, k: float) -> None:
    """Raises ValueError unless k >= 0 (also used for "k" defects)."""
    if not k >= 0:
        raise ParamError(node, "conductance_negative", key="k", value=k)
