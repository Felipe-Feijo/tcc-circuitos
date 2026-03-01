from simulation.nodes.nodes import Node


class DirectOperatedReliefValve(Node):
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id, "direct_operated_relief_valve", **kwargs)

        if self.domain == "hydraulic":
            self.p_set       = self.properties.get("p_set", 10)
            self._open       = False
            self.flow_var_in  = f"Q_{self.id}_in"
            self.flow_var_out = f"Q_{self.id}_out"

    @property
    def variables(self) -> list:
        if self.domain != "hydraulic":
            return []
        vars = [self.flow_var_in, self.flow_var_out]
        for anchor_name in self.hydraulic_ports().keys():
            anchor = self.anchors.get(anchor_name)
            if anchor and anchor.pressure_var:
                vars.append(anchor.pressure_var)
        return vars

    def hydraulic_ports(self) -> dict:
        if self.domain != "hydraulic":
            return {}
        return {
            "P": self.flow_var_in,
            "T": self.flow_var_out,
        }

    def equations(self, x, idx) -> list:
        Q_in  = x[idx[self.flow_var_in]]
        Q_out = x[idx[self.flow_var_out]]
        P_in  = x[idx[self.anchors["P"].pressure_var]]

        if self._open:
            return [
                Q_in + Q_out,
                P_in - self.p_set,
            ]

        return [Q_in, Q_out]

    @property
    def initial_guess(self) -> dict:
        if self.domain != "hydraulic":
            return {}
        if not self._open:
            return {
                self.flow_var_in:  0.0,
                self.flow_var_out: 0.0,
            }

        anchor_p = self.anchors.get("P")
        p_var = anchor_p.pressure_var if anchor_p else None

        guess = {
            self.flow_var_in:   1.0,
            self.flow_var_out: -1.0,
        }
        if p_var:
            guess[p_var] = self.p_set
        return guess

    def open_relief(self):
        """Chamado pela engine quando o circuito falha sem saída."""
        self._open = True

    def update(self, outputs=None):
        """Abre/fecha baseado na pressão do step anterior."""
        if self.domain != "hydraulic":
            return
        anchor = self.anchors.get("P")
        if anchor is None or isinstance(anchor.pressure, str):
            return
        self._open = anchor.pressure >= self.p_set

    def get_state(self):
        state = super().get_state()
        if self.domain == "hydraulic":
            state["_open"] = self._open
        return state

    def set_state(self, state):
        super().set_state(state)
        if self.domain == "hydraulic":
            self._open = state.get("_open", self._open)