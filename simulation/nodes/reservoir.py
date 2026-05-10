from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin

class Reservoir(Node, HydraulicMixin):

    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "reservoir", domain=domain, properties=properties)
        self.pressure = self.properties.get("pressure", 0.0)
        self.flow_var = f"Q_{self.id}"  # Q livre, absorve/fornece o que precisar

    @property
    def variables(self):
        return [self.flow_var]
    
    @property
    def flow_hint(self) -> float:
        # reservoir sempre pode fornecer/absorver fluxo
        # usa um valor padrão pequeno como referência de escala
        return 0
    
    @property
    def p_hint(self) -> float:
        return self.pressure  # normalmente 0

    def hydraulic_ports(self):
        return {"T": self.flow_var}  # participa da continuidade do grupo

    def equations(self, x, idx):
        anchor = self.anchors["T"]
        pvar = anchor.pressure_var
        return [x[idx[pvar]] - self.pressure]