import math
from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin

class DoubleActingCylinder(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "double_acting_cylinder", domain=domain, properties=properties)

        default = self.properties.get("default_state", "retracted")
        self.position = 1 if default == "extended" else 0

        self.sensors = self.properties.get("sensors", {
            "retracted": {"type": None, "name": ""},
            "extended":  {"type": None, "name": ""},
        })

        self.outputs = {}

        if self.domain == "hydraulic":
            for key in ("bore", "rod_diameter", "stroke"):
                if self.properties.get(key) is None:
                    raise ValueError(
                        f"DoubleActingCylinder '{self.id}': propriedade obrigatória '{key}' não preenchida."
                    )
            bore     = float(self.properties["bore"])
            rod      = float(self.properties["rod_diameter"])
            self.area_a = math.pi * (bore / 2) ** 2
            self.area_b = self.area_a - math.pi * (rod / 2) ** 2
            self.stroke         = float(self.properties["stroke"])
            self.external_force = float(self.properties.get("external_force") or 0.0)
            self.friction       = 1e-3   # oculto — valor mínimo para fechar a conta
            stroke = float(self.properties["stroke"])
            self.x = stroke if default == "extended" else 0.0
            self.locked_fwd     = False
            self.locked_bwd     = False
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

        anchor_a = self.anchors.get("A")
        P_a = getattr(anchor_a, "pressure", 0.0) if anchor_a else 0.0
        if isinstance(P_a, str):
            P_a = 0.0

        anchor_b = self.anchors.get("B")
        P_b = getattr(anchor_b, "pressure", 0.0) if anchor_b else 0.0
        if isinstance(P_b, str):
            P_b = 0.0

        EPS = self.stroke * 1e-4

        if self.x <= EPS or self.x >= self.stroke - EPS:
            return {self.flow_var_a: 0.0, self.flow_var_b: 0.0}

        F_hidro = P_a * self.area_a - P_b * self.area_b
        F_net   = F_hidro - self.external_force
        v_eq    = F_net / self.friction
        Q_eq    = v_eq * self.area_a

        return {
            self.flow_var_a:  Q_eq,
            self.flow_var_b: -Q_eq,
        }

    def hydraulic_ports(self):
        if self.domain != "hydraulic":
            return {}
        return {
            "A": self.flow_var_a,
            "B": self.flow_var_b,
        }
        

    def _fb(self, a, b):
        return a + b - math.sqrt(a*a + b*b)

    def equations(self, x, idx):
        Q_a = x[idx[self.flow_var_a]]
        Q_b = x[idx[self.flow_var_b]]
        P_a = x[idx[self.anchors["A"].pressure_var]]
        P_b = x[idx[self.anchors["B"].pressure_var]]

        v       = Q_a / self.area_a
        F_hidro = P_a * self.area_a - P_b * self.area_b
        F_res   = self.external_force + self.friction * v
        F_net   = F_hidro - F_res

        F_scale = max(abs(F_hidro), abs(F_res), 1.0)
        Q_scale = max(self.area_a * self.stroke, 1e-8)

        f = F_net / F_scale
        q = Q_a   / Q_scale

        EPS = self.stroke * 1e-4

        # Conservação sempre vale
        eq_conservation = Q_a + Q_b

        if self.x <= EPS:
            # Proibido: Q_a < 0 (não pode recuar além do batente)
            # φ(q, -f) = 0
            return [self._fb(q, -f), eq_conservation]

        if self.x >= self.stroke - EPS:
            # Proibido: Q_a > 0 (não pode avançar além do batente)
            # φ(-q, f) = 0
            return [self._fb(-q, f), eq_conservation]

        return [f, eq_conservation]

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