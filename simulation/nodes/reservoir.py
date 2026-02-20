from simulation.nodes.nodes import Node

class Reservoir(Node):

    def __init__(self, node_id, **kwargs):
        super().__init__(node_id, "reservoir", **kwargs)
        self.pressure = self.properties.get("pressure", 0.0)
        self.flow_var = f"Q_{self.id}"  # Q livre, absorve/fornece o que precisar

    @property
    def variables(self):
        anchor = self.anchors.get("R")
        pvar = getattr(anchor, "pressure_var", None) if anchor else None
        return ([pvar] if pvar else []) + [self.flow_var]

    def hydraulic_ports(self):
        return {"R": self.flow_var}  # participa da continuidade do grupo

    def equations(self, x, idx):
        anchor = self.anchors.get("R")
        pvar = getattr(anchor, "pressure_var", None) if anchor else None
        if not pvar or pvar not in idx:
            return []
        return [x[idx[pvar]] - self.pressure]  # só fixa P, Q fica livre