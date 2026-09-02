"""Simulation node for the pressure gauge (pneumatic and hydraulic).

Purely passive tap: a single dead-end port that reads whatever
pressure/state already exists at the point it's wired to, without
affecting the rest of the circuit.

Hydraulic: modeled as a dead port, same technique as the check valve's
pilot port (simulation/nodes/check_valve/check_valve.py) -- it needs
its own flow variable and an explicit Q=0 equation to close the
system. Without that equation, the shared pressure variable at the tap
point would never be guaranteed to enter the solve when nothing else
in the circuit references this node's port.

Pneumatic: no equations of its own -- the anchor's `state` is set by
the normal pneumatic domain propagation
(SimulationEngine._update_pneumatic_domain); this node is never a
driver.
"""

from __future__ import annotations

from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin


class PressureGauge(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "pressure_gauge", domain=domain, properties=properties)

        if self.domain == "hydraulic":
            self.flow_var = f"Q_{self.id}_P"

    def get_visual_state(self):
        anchor = self.anchors["P"]
        return anchor.pressure if self.domain == "hydraulic" else anchor.state

    @property
    def variables(self):
        if self.domain != "hydraulic":
            return []
        vars_ = [self.flow_var]
        anchor = self.anchors.get("P")
        if anchor and anchor.pressure_var:
            vars_.append(anchor.pressure_var)
        return vars_

    def hydraulic_ports(self):
        if self.domain != "hydraulic":
            return {}
        return {"P": self.flow_var}

    def equations(self, x, idx):
        Q = x[idx[self.flow_var]]
        return [Q / max(self.q_ref, 1e-12)]
