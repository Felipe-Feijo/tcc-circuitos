"""
simulation/hydraulic/

Hydraulic domain of the simulation.

Main exports
------------
HydraulicNode     : Protocol every hydraulic node must satisfy
HydraulicMixin    : Mixin with defaults for optional members
ScaleContext      : immutable scale context per solve
ScaleManager      : estimates p_ref and q_ref from the nodes
ZcScheduler       : computes zc as a function of the iteration
NodeContinuity    : virtual pressurization capacitor
NonlinearSystemSolver : solves the equation system
ConvergenceMonitor    : checks flow conservation
ConvergenceResult     : verification result
"""

from simulation.hydraulic.node_protocol import HydraulicNode, HydraulicMixin
from simulation.hydraulic.scale_context import (
    ScaleContext,
    ScaleManager,
    ZcScheduler,
    DEFAULT_P_REF,
    DEFAULT_Q_REF,
)
from simulation.hydraulic.solver import NodeContinuity, NonlinearSystemSolver
from simulation.hydraulic.convergence import ConvergenceMonitor, ConvergenceResult

__all__ = [
    "HydraulicNode",
    "HydraulicMixin",
    "ScaleContext",
    "ScaleManager",
    "ZcScheduler",
    "DEFAULT_P_REF",
    "DEFAULT_Q_REF",
    "NodeContinuity",
    "NonlinearSystemSolver",
    "ConvergenceMonitor",
    "ConvergenceResult",
]