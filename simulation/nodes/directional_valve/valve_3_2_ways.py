import math

from simulation.nodes.directional_valve.directional_valve import DirectionalValve


class Valve_3_2_Ways(DirectionalValve):
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id, "valve_3_2_ways", **kwargs)

    def get_internal_connections(self):
        if self.body_state == 0:
            return [("A", "R")]
        elif self.body_state == 1:
            return [("P", "A")]

    # ------------------------------------------------------------------
    # Domínio hidráulico
    # ------------------------------------------------------------------

    @property
    def variables(self):
        vars = [f"Q_{self.id}_in", f"Q_{self.id}_out"]
        for anchor_name in self.hydraulic_ports().keys():
            anchor = self.anchors.get(anchor_name)
            if anchor and anchor.pressure_var:
                vars.append(anchor.pressure_var)
        return vars

    def hydraulic_ports(self):
        if self.body_state == 1:  # P → A
            return {
                "P": f"Q_{self.id}_in",
                "A": f"Q_{self.id}_out",
            }
        else:  # A → R
            return {
                "A": f"Q_{self.id}_in",
                "R": f"Q_{self.id}_out",
            }

    def equations(self, x, idx):
        Q_in  = x[idx[f"Q_{self.id}_in"]]
        Q_out = x[idx[f"Q_{self.id}_out"]]
        k = self.properties.get("k", 0.0001)

        if self.body_state == 1:
            P_in  = x[idx[self.anchors["P"].pressure_var]]
            P_out = x[idx[self.anchors["A"].pressure_var]]
        else:
            P_in  = x[idx[self.anchors["A"].pressure_var]]
            P_out = x[idx[self.anchors["R"].pressure_var]]

        delta_p = P_in - P_out

        return [
            Q_in + Q_out,
            delta_p - math.copysign((Q_in / k) ** 2, Q_in)
        ]

    def initial_guess(self):
        if self.domain != "hydraulic":
            return {}
        # sentinelas — serão escalados pelo flow_hint da bomba
        # sinal oposto garante Q_in + Q_out = 0 desde o início
        return {
            f"Q_{self.id}_in":   1.0,
            f"Q_{self.id}_out": -1.0,
        }