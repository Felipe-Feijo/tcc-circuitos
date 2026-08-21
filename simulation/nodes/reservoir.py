"""Simulation node for the hydraulic reservoir."""

from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin

class Reservoir(Node, HydraulicMixin):

    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "reservoir", domain=domain, properties=properties)
        self.pressure = self.properties.get("pressure", 0.0)
        self.flow_var = f"Q_{self.id}"  # free Q, absorbs/supplies whatever is needed

    @property
    def variables(self):
        return [self.flow_var]
    
    @property
    def flow_hint(self) -> float:
        # reservoir can always supply/absorb flow
        # uses a small default value as a scale reference
        return 0
    
    @property
    def p_hint(self) -> float:
        return self.pressure  # normally 0

    def hydraulic_ports(self):
        return {"T": self.flow_var}  # participates in the group's continuity

    def equations(self, x, idx):
        anchor = self.anchors["T"]
        pvar = anchor.pressure_var
        return [x[idx[pvar]] - self.pressure]