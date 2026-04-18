import math
from simulation.nodes.nodes import Node

class SingleActingCylinder(Node):
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id, "single_acting_cylinder", **kwargs)

        self.position = 0

        self.sensors = self.properties.get("sensors", {
            "retracted": {"type": None, "name": ""},
            "extended":  {"type": None, "name": ""}
        })

        self.outputs = {}

        if self.domain == "hydraulic":
            bore                 = self.properties["bore"]
            self.area            = math.pi * (bore / 2) ** 2
            self.stroke          = self.properties["stroke"]
            self.spring_k        = self.properties["spring_k"]
            self.external_force  = self.properties["external_force"]
            self.friction        = max(self.properties["friction"], 1e-3)
            self.x               = 0.0
            self.flow_var        = f"Q_{self.id}"

            # Batente spring-damper
            F_worst = max(
                abs(self.external_force),
                self.spring_k * self.stroke,
                1.0
            )
            self.k_end = self.properties.get(
                "k_end",
                max(
                    self.spring_k * 1e4,
                    F_worst / (self.stroke * 1e-6),
                    1e8
                )
            )
            self.c_end = self.properties.get(
                "c_end",
                2.0 * math.sqrt(self.k_end * self.area ** 2 / self.friction)
            )

    # ------------------------------------------------------------------
    # Helpers de batente
    # ------------------------------------------------------------------

    def _contact_force(self, x, v) -> float:
        """Força de contato nos batentes (sempre empurra de volta para o stroke)."""
        pen_ret = max(0.0, -x)                    # penetração no batente retraído
        pen_ext = max(0.0, x - self.stroke)       # penetração no batente estendido

        F = 0.0
        if pen_ret > 0:
            F += self.k_end * pen_ret - self.c_end * min(v, 0.0)   # v negativo = entrando
        if pen_ext > 0:
            F -= self.k_end * pen_ext - self.c_end * max(v, 0.0)   # v positivo = entrando

        return F

    # ------------------------------------------------------------------
    # Contrato hidráulico
    # ------------------------------------------------------------------

    @property
    def variables(self):
        if self.domain != "hydraulic":
            return []
        anchor = self.anchors["A"]
        pvar = getattr(anchor, "pressure_var", None) if anchor else None
        return ([pvar] if pvar else []) + [self.flow_var]

    @property
    def flow_hint(self) -> float:
        F_mola = self.spring_k * self.x
        F_net  = F_mola + self.external_force
        if F_net <= 0:
            return 0.0
        return (F_net / self.friction) * self.area

    @property
    def p_hint(self) -> float:
        F = self.spring_k * self.x + self.external_force
        return F / self.area if self.area > 0 else 0.0

    @property
    def initial_guess(self):
        if self.domain != "hydraulic":
            return {}
        anchor  = self.anchors["A"]
        P_prev  = getattr(anchor, "pressure", 0.0)
        if isinstance(P_prev, str):
            P_prev = 0.0
        F_mola = self.spring_k * self.x
        F_net  = P_prev * self.area - F_mola - self.external_force
        Q_eq   = (F_net / max(self.friction, 1e-3)) * self.area
        return {self.flow_var: Q_eq}

    def hydraulic_ports(self):
        if self.domain != "hydraulic":
            return {}
        return {"A": self.flow_var}

    @property
    def bounds(self):
        if self.domain != "hydraulic":
            return {}

        EPS = self.stroke * 1e-3

        if self.x <= EPS:
            return {self.flow_var: (0.0, None)}    # só avança
        elif self.x >= self.stroke - EPS:
            return {self.flow_var: (None, 0.0)}    # só recua

        return {}

    def equations(self, x, idx):
        Q = x[idx[self.flow_var]]
        P = x[idx[self.anchors["A"].pressure_var]]
        EPS = self.stroke * 1e-3
        v       = Q / self.area
        F_hidro = P * self.area
        F_mola  = self.spring_k * self.x
        F_res   = F_mola + self.external_force + self.friction * v

        # no batente retraído com força empurrando para fora
        if self.x <= EPS and F_hidro <= F_res:
            F_scale = max(abs(F_res), 1.0)
            return [Q / (self.area * F_scale)]  # força Q → 0

        # no batente estendido com força empurrando para dentro
        if self.x >= self.stroke - EPS and F_hidro >= F_res:
            F_scale = max(abs(F_hidro), 1.0)
            return [Q / (self.area * F_scale)]  # força Q → 0

        # zona livre — equilíbrio de forças normal
        F_contact = self._contact_force(self.x, v)
        F_res     = F_res - F_contact
        F_net     = F_hidro - F_res
        F_scale   = max(abs(F_hidro), abs(F_res), 1.0)
        return [F_net / F_scale]

    # ------------------------------------------------------------------
    # Update lógico
    # ------------------------------------------------------------------

    def update(self, outputs=None):
        if self.domain != "hydraulic":
            self.position = 1 if self.anchors["A"].state else 0

    # ------------------------------------------------------------------
    # Post step
    # ------------------------------------------------------------------

    def post_step_update(self, dt=None):
        super().post_step_update(dt=dt)

        # sensores
        if self.sensors["retracted"]["type"]:
            name = self.sensors["retracted"]["name"]
            self.outputs[name] = {"type": "signal", "value": self.position == 0}

        if self.sensors["extended"]["type"]:
            name = self.sensors["extended"]["name"]
            self.outputs[name] = {"type": "signal", "value": self.position == 1}

        if self.domain == "hydraulic" and dt is not None:
            anchor = self.anchors["A"]
            if anchor and not isinstance(anchor.flow, str):
                self.x += (anchor.flow / self.area) * dt
                if self.x > self.stroke:
                    self.x = self.stroke
                elif self.x < 0:
                    self.x = 0

                # position: 0 ou 1 com threshold de 1% do stroke
                if self.stroke > 0:
                    ratio = self.x / self.stroke
                    if ratio < 0.01:
                        self.position = 0
                    elif ratio > 0.99:
                        self.position = 1
                    else:
                        self.position = round(ratio)
            print(self.x, self.position)


    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    def get_visual_state(self):
        if self.domain == "hydraulic" and self.stroke > 0:
            return max(0.0, min(1.0, self.x / self.stroke))
        return self.position

    def get_state(self):
        state = super().get_state()
        state["position"] = self.position
        if self.domain == "hydraulic":
            state["x"] = self.x
        return state

    def set_state(self, state):
        super().set_state(state)
        self.position = state.get("position", self.position)
        if self.domain == "hydraulic":
            self.x = state.get("x", self.x)