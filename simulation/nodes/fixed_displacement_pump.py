from simulation.nodes.nodes import Node

class FixedDisplacementPump(Node):
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id, "fixed_displacement_pump", **kwargs)
        self.flow_in_var  = f"Q_{self.id}_P"   # sucção (P = inlet)
        self.flow_out_var = f"Q_{self.id}_S"   # descarga (S = outlet)

    @property
    def flow_hint(self) -> float:
        return self.properties.get("Q", 1e-4)

    @property
    def variables(self):
        return [self.flow_in_var, self.flow_out_var]

    def hydraulic_ports(self):
        return {
            "P": self.flow_in_var,
            "S": self.flow_out_var,
        }

    def equations(self, x, idx):
        Q_in  = x[idx[self.flow_in_var]]
        Q_out = x[idx[self.flow_out_var]]
        Q_set = self.properties["Q"]

        # Conservação interna: o que entra sai
        # Imposição de vazão: a saída é Q_set
        # Convenção: Q_in positivo = entrando na bomba, Q_out positivo = saindo
        return [
            Q_in + Q_out,        # Q_in = -Q_out (conservação)
            Q_out - Q_set,       # Q_out = Q_set (bomba fixa)
        ]