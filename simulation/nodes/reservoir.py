from simulation.nodes.nodes import Node

class Reservoir(Node):

    def __init__(self, node_id, **kwargs):
        super().__init__(node_id, "reservoir", **kwargs)
        self.pressure = self.properties.get("pressure", 0.0)
        self.flow_var = f"Q_{self.id}"  # Q livre, absorve/fornece o que precisar

    @property
    def variables(self):
        return [self.flow_var]
    
    @property
    def flow_hint(self) -> float:
        # reservoir sempre pode fornecer/absorver fluxo
        # usa um valor padrão pequeno como referência de escala
        return 1e-4

    def hydraulic_ports(self):
        return {"R": self.flow_var}  # participa da continuidade do grupo

    def equations(self, x, idx):
        anchor = self.anchors["R"]
        pvar = anchor.pressure_var
        return [x[idx[pvar]] - self.pressure]