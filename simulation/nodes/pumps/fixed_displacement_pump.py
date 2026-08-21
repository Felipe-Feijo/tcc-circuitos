"""Fixed-displacement pump simulation node (hydraulic domain)."""

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
                raise ValueError(f"FixedDisplacementPump '{self.id}': required property 'Q' is not set.")
            self.Q_set = float(Q)
            # Names kept for compatibility: flow_in_var maps to port P
            # (discharge/pressure, sprite top), flow_out_var to port S
            # (suction, bottom, connected to the reservoir). "in"/"out"
            # label the equation-system variable pair only; physical flow
            # direction is set by the forced values below.
            self.flow_in_var  = f"Q_{self.id}_P"
            self.flow_out_var = f"Q_{self.id}_S"

    @property
    def is_flow_source(self) -> bool:
        return True

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

        # Internal conservation: inflow equals outflow.
        # Flow imposition: outlet is Q_set.
        # Domain convention (simulation/hydraulic/node_protocol.py): Q > 0
        # means fluid ENTERING the component at that port. Fluid EXITS
        # the pump through P (discharge/pressure), so Q_in (port P's
        # variable) is forced NEGATIVE; fluid ENTERS through S (suction),
        # so Q_out (port S's variable) is forced POSITIVE. "Q_in"/"Q_out"
        # are variable-pair labels only, not a description of physical direction.
        return [
            Q_in + Q_out,        # Q_in = -Q_out (conservation)
            Q_out - self.Q_set,       # Q_out = Q_set (fixed-displacement pump)
        ]
