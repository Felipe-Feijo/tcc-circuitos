"""
simulation/hydraulic/node_protocol.py

Formal contract for hydraulic-domain nodes.

Sign convention (adopted throughout the domain):
  Q > 0  =>  fluid ENTERING the node through the port
  Q < 0  =>  fluid EXITING  the node through the port

Every hydraulic node must inherit from HydraulicMixin and implement
the abstract methods: variables, hydraulic_ports, equations.

The HydraulicNode Protocol allows an isinstance() check without
inheritance, but the engine's real detection uses HydraulicMixin as
the base.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
import numpy as np


@runtime_checkable
class HydraulicNode(Protocol):
    """
    Structural protocol -- allows isinstance(node, HydraulicNode).
    Checked at runtime by the engine to collect hydraulic nodes.

    Minimal implementation: variables, hydraulic_ports, equations.
    Defaults for the rest: use HydraulicMixin as your class's base.
    """

    @property
    def variables(self) -> list[str]: ...
    def hydraulic_ports(self) -> dict[str, str]: ...
    def equations(self, x: np.ndarray, idx: dict[str, int]) -> list[float]: ...
    def set_scale(self, p_ref: float, q_ref: float) -> None: ...

    @property
    def flow_hint(self) -> float: ...
    @property
    def p_hint(self) -> float: ...
    @property
    def bounds(self) -> dict: ...
    @property
    def initial_guess(self) -> dict: ...


class HydraulicMixin:
    """
    Mixin with default implementations for the contract's optional members.

    Usage:
        class MyValve(Node, HydraulicMixin):
            ...  # only needs to implement variables, hydraulic_ports, equations

    Members with a default (can override):
        bounds        -> {} (no bounds)
        set_scale     -> stores p_ref/q_ref in self.p_ref / self.q_ref
        flow_hint     -> 0.0
        p_hint        -> 0.0
        initial_guess -> {}

    Required members (must implement):
        variables      (property)
        hydraulic_ports (method)
        equations       (method)
    """

    # Default scale for the industrial range (50-300 bar)
    # Overwritten by set_scale() before each solve
    p_ref: float = 100 * 1e5   # Pa -- 100 bar
    q_ref: float = 20 / 60_000  # m3/s -- 20 L/min

    @property
    def bounds(self) -> dict[str, tuple[float | None, float | None]]:
        """No bounds by default."""
        return {}

    def set_scale(self, p_ref: float, q_ref: float) -> None:
        """Stores p_ref and q_ref for use in equations()."""
        self.p_ref = max(p_ref, 1e5)    # minimum 1 bar
        self.q_ref = max(q_ref, 1e-10)

    @property
    def flow_hint(self) -> float:
        """Characteristic flow estimate. Override for better scaling."""
        return 0.0

    @property
    def p_hint(self) -> float:
        """Characteristic pressure estimate. Override for better scaling."""
        return 0.0

    @property
    def initial_guess(self) -> dict[str, float]:
        """Empty initial guess -- the solver uses the global Q_hint."""
        return {}