import math
from simulation.nodes.nodes import Node

class SingleActingCylinder(Node):
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id, "single_acting_cylinder", **kwargs)

        # Estado lógico (pneumático)
        self.position = 0

        self.sensors = self.properties.get("sensors", {
            "retracted": {"type": None, "name": ""},
            "extended": {"type": None, "name": ""}
        })

        self.outputs = {}

        # Estado hidráulico (só inicializa se domínio for hidráulico)
        if self.domain == "hydraulic":
            bore             = self.properties["bore"]
            self.area        = math.pi * (bore / 2) ** 2
            self.stroke      = self.properties["stroke"]
            self.spring_k = self.properties["spring_k"]
            self.external_force = self.properties["external_force"]
            self.friction       = self.properties["friction"]
            self.x      = 0.0
            self.locked = False
            self.flow_var = f"Q_{self.id}"

    # ------------------------------------------------------------------
    # Contrato hidráulico (só exposto se domain == "hydraulic")
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
        if self.locked:
            return 0.0
        F_mola = self.spring_k * self.x
        F_net  = F_mola + self.external_force
        friction_eff = max(self.friction, 1e-3)
        v_hint = F_net / friction_eff
        hint = abs(v_hint * self.area)
        # fallback: se não há força, usa flow_rate da bomba ou valor mínimo
        return hint if hint > 1e-10 else 0.0  # retorna 0 — bomba vai fornecer o hint
    
    @property
    def initial_guess(self):
        if self.domain != "hydraulic":
            return {}

        # força líquida disponível para mover o pistão
        F_mola = self.spring_k * self.x
        F_net  = F_mola + self.external_force

        if F_net > 0 and self.area > 0:
            # estima velocidade de recuo pela força disponível
            # sem fricção, usa área como escala de referência
            denom = self.friction if self.friction > 0 else 1.0
            v_hint = F_net / denom
            Q_hint = -v_hint * self.area  # negativo = saindo do cilindro
        else:
            Q_hint = 0.0

        return {self.flow_var: Q_hint}

    def hydraulic_ports(self):
        if self.domain != "hydraulic":
            return {}
        return {"A": self.flow_var}

    def equations(self, x, idx):
        Q = x[idx[self.flow_var]]
        P = x[idx[self.anchors["A"].pressure_var]]
        v       = Q / self.area
        F_hidro = P * self.area
        F_mola  = self.spring_k * self.x
        F_res   = F_mola + self.external_force + self.friction * v

        if self.locked:
            # só bloqueia entrada (Q > 0), permite saída (Q < 0)
            if Q > 0:
                return [Q]
            # se Q < 0, aplica física normal — cilindro pode recuar
        
        return [F_hidro - F_res]
    

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

        # sensores — independente do domínio
        if self.sensors["retracted"]["type"]:
            name = self.sensors["retracted"]["name"]
            self.outputs[name] = {
                "type": "signal",
                "value": self.position == 0
            }

        if self.sensors["extended"]["type"]:
            name = self.sensors["extended"]["name"]
            self.outputs[name] = {
                "type": "signal",
                "value": self.position == 1
            }

        # integração hidráulica
        if self.domain == "hydraulic" and dt is not None:
            anchor = self.anchors["A"]
            if anchor and not isinstance(anchor.flow, str):

                # desbloqueia se há fluxo saindo — fora do guard de locked
                if self.locked and anchor.flow < 0:
                    self.locked = False

                if not self.locked:
                    self.x += (anchor.flow / self.area) * dt
                    self.x  = max(0.0, min(self.x, self.stroke))

                    self.position = round(self.x / self.stroke) if self.stroke > 0 else 0

                    if self.x >= self.stroke:
                        self.locked = True
        print("pos", self.position, "x", self.x, "locked", self.locked)

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    def get_visual_state(self):
        #if self.domain == "hydraulic" and self.stroke > 0:
        #    return self.x / self.stroke
        return self.position

    def get_state(self):
        state = super().get_state()
        state["position"] = self.position
        if self.domain == "hydraulic":
            state["x"]      = self.x
            state["locked"] = self.locked
        return state

    def set_state(self, state):
        super().set_state(state)
        self.position = state.get("position", self.position)
        if self.domain == "hydraulic":
            self.x      = state.get("x", self.x)
            self.locked = state.get("locked", self.locked)