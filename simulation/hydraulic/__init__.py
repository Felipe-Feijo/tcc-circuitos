"""
simulation/hydraulic/

Domínio hidráulico da simulação.

Exports principais
------------------
HydraulicNode     : Protocol que todo nó hidráulico deve satisfazer
HydraulicMixin    : Mixin com defaults para membros opcionais
ScaleContext      : contexto de escala imutável por solve
ScaleManager      : estima p_ref e q_ref a partir dos nós
ZcScheduler       : calcula zc em função da iteração
NodeContinuity    : capacitor virtual de pressurização
NonlinearSystemSolver : resolve o sistema de equações
ConvergenceMonitor    : verifica conservação de vazão
ConvergenceResult     : resultado da verificação
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