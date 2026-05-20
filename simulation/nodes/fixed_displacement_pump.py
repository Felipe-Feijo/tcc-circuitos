from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin

class FixedDisplacementPump(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "fixed_displacement_pump", domain=domain, properties=properties)
        self.setup()

    def setup(self):
        if self.domain == "hydraulic":
            Q = self.properties.get("Q")
            if Q is None:
                raise ValueError(f"FixedDisplacementPump '{self.id}': propriedade obrigatória 'Q' não preenchida.")
            self.Q_set = float(Q)
            self.flow_in_var  = f"Q_{self.id}_P"
            self.flow_out_var = f"Q_{self.id}_S"

    @property
    def flow_hint(self) -> float:
        return self.Q_set

    @property
    def variables(self):
        return [self.flow_in_var, self.flow_out_var]
    
    @property
    def bounds(self):
        eps = self.Q_set * 1e-6
        return {
            self.flow_in_var:  (-self.Q_set - eps, -self.Q_set + eps),
            self.flow_out_var: (self.Q_set - eps, self.Q_set + eps)
        }
    
    @property
    def initial_guess(self):
        return {
            self.flow_in_var:  self.Q_set,
            self.flow_out_var: -self.Q_set,
        }

    def hydraulic_ports(self):
        return {
            "P": self.flow_in_var,
            "S": self.flow_out_var,
        }

    def equations(self, x, idx):
        Q_in  = x[idx[self.flow_in_var]]
        Q_out = x[idx[self.flow_out_var]]

        # Conservação interna: o que entra sai
        # Imposição de vazão: a saída é Q_set
        # Convenção: Q_in positivo = entrando na bomba, Q_out positivo = saindo
        return [
            Q_in + Q_out,        # Q_in = -Q_out (conservação)
            Q_out - self.Q_set,       # Q_out = Q_set (bomba fixa)
        ]
    