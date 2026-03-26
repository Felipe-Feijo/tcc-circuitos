import math
from simulation.nodes.nodes import Node


class DoubleActingCylinder(Node):
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id, "double_acting_cylinder", **kwargs)

        self.position = 0

        self.sensors = self.properties.get("sensors", {
            "retracted": {"type": None, "name": ""},
            "extended":  {"type": None, "name": ""},
        })

        self.outputs = {}

        if self.domain == "hydraulic":
            bore     = self.properties["bore"]
            rod      = self.properties["rod_diameter"]
            self.area_a = math.pi * (bore / 2) ** 2
            self.area_b = self.area_a - math.pi * (rod / 2) ** 2
            self.stroke         = self.properties["stroke"]
            self.external_force = self.properties["external_force"]
            self.friction       = max(self.properties["friction"], 1e-3)
            self.x              = 0.0
            self.locked_fwd     = False  # travado no avanço (x >= stroke)
            self.locked_bwd     = False  # travado no recuo  (x <= 0)
            self.flow_var_a     = f"Q_{self.id}_a"
            self.flow_var_b     = f"Q_{self.id}_b"

    # ------------------------------------------------------------------
    # Contrato hidráulico
    # ------------------------------------------------------------------

    @property
    def variables(self):
        if self.domain != "hydraulic":
            return []
        vars = [self.flow_var_a, self.flow_var_b]
        for name in ("A", "B"):
            anchor = self.anchors.get(name)
            pvar = getattr(anchor, "pressure_var", None) if anchor else None
            if pvar:
                vars.append(pvar)
        return vars

    @property
    def flow_hint(self) -> float:
        if self.locked_fwd or self.locked_bwd:
            return 0.0
        F_net = self.external_force
        hint = abs(F_net / self.friction * self.area_a)
        return hint if hint > 1e-10 else 0.0

    @property
    def initial_guess(self):
        if self.domain != "hydraulic":
            return {}
        # chuta avanço por padrão — Q_a positivo, Q_b negativo (conservação)
        Q_hint = self.flow_hint if self.flow_hint > 0 else 1e-4
        return {
            self.flow_var_a:  Q_hint,
            self.flow_var_b: -Q_hint,
        }

    def hydraulic_ports(self):
        if self.domain != "hydraulic":
            return {}
        return {
            "A": self.flow_var_a,
            "B": self.flow_var_b,
        }
        

    def equations(self, x, idx):
        Q_a = x[idx[self.flow_var_a]]
        Q_b = x[idx[self.flow_var_b]]
        P_a = x[idx[self.anchors["A"].pressure_var]]
        P_b = x[idx[self.anchors["B"].pressure_var]]

        v       = Q_a / self.area_a
        F_hidro = P_a * self.area_a - P_b * self.area_b
        F_res   = self.external_force + self.friction * v

        # trava avanço — só permite recuar (Q_a < 0)
        if self.locked_fwd and Q_a > 0:
            return [Q_a, Q_a + Q_b]

        # trava recuo — só permite avançar (Q_a > 0)
        if self.locked_bwd and Q_a < 0:
            return [Q_a, Q_a + Q_b]

        return [
            F_hidro - F_res,   # equilíbrio de forças
            Q_a + Q_b,         # conservação de fluxo (incompressível)
        ]

    # ------------------------------------------------------------------
    # Update lógico
    # ------------------------------------------------------------------

    def update(self, outputs=None):
        if self.domain != "hydraulic":
            a = self.anchors["A"].state
            b = self.anchors["B"].state

            if a:                # 10 ou 11 — avança
                self.position = 1
            elif b:              # 01 — recua
                self.position = 0
            # 00 — mantém

    # ------------------------------------------------------------------
    # Post step
    # ------------------------------------------------------------------

    def post_step_update(self, dt=None):
        super().post_step_update(dt=dt)

        if self.sensors["retracted"]["type"]:
            name = self.sensors["retracted"]["name"]
            self.outputs[name] = {"type": "signal", "value": self.position == 0}

        if self.sensors["extended"]["type"]:
            name = self.sensors["extended"]["name"]
            self.outputs[name] = {"type": "signal", "value": self.position == 1}

        if self.domain == "hydraulic" and dt is not None:
            self._integrate_hydraulic(dt)

    def _integrate_hydraulic(self, dt):
        anchor_a = self.anchors.get("A")
        if not anchor_a or isinstance(anchor_a.flow, str):
            return

        Q_a = anchor_a.flow

        # desbloqueia se o fluxo inverteu
        if self.locked_fwd and Q_a < 0:
            self.locked_fwd = False
        if self.locked_bwd and Q_a > 0:
            self.locked_bwd = False

        if not self.locked_fwd and not self.locked_bwd:
            self.x += (Q_a / self.area_a) * dt
            self.x  = max(0.0, min(self.x, self.stroke))

            self.position = round(self.x / self.stroke) if self.stroke > 0 else 0

            if self.x >= self.stroke:
                self.locked_fwd = True
            if self.x <= 0.0:
                self.locked_bwd = True

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    def get_visual_state(self):
        if self.domain == "hydraulic" and self.stroke > 0:
            return self.x / self.stroke
        return self.position

    def get_state(self):
        state = super().get_state()
        state["position"] = self.position
        if self.domain == "hydraulic":
            state["x"]          = self.x
            state["locked_fwd"] = self.locked_fwd
            state["locked_bwd"] = self.locked_bwd
        return state

    def set_state(self, state):
        super().set_state(state)
        self.position = state.get("position", self.position)
        if self.domain == "hydraulic":
            self.x          = state.get("x", self.x)
            self.locked_fwd = state.get("locked_fwd", self.locked_fwd)
            self.locked_bwd = state.get("locked_bwd", self.locked_bwd)