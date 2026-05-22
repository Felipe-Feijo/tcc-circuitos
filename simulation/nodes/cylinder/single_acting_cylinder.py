"""Nó de simulação de cilindro de simples ação."""

import math
from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin

class SingleActingCylinder(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "single_acting_cylinder", domain=domain, properties=properties)

        default = self.properties.get("default_state", "retracted")
        self.position = 1 if default == "extended" else 0

        self.sensors = self.properties.get("sensors", {
            "retracted": {"type": None, "name": ""},
            "extended":  {"type": None, "name": ""}
        })

        self.outputs = {}

        # Inicializa outputs dos sensores com base no default_state,
        # para que o valor já seja correto antes do primeiro step de simulação.
        if self.sensors["retracted"]["type"]:
            name = self.sensors["retracted"]["name"]
            if name:
                self.outputs[name] = {"type": "signal", "value": self.position == 0}

        if self.sensors["extended"]["type"]:
            name = self.sensors["extended"]["name"]
            if name:
                self.outputs[name] = {"type": "signal", "value": self.position == 1}

        if self.domain == "hydraulic":
            for key in ("bore", "stroke", "spring_k"):
                if self.properties.get(key) is None:
                    raise ValueError(
                        f"SingleActingCylinder '{self.id}': propriedade obrigatória '{key}' não preenchida."
                    )
            bore                 = float(self.properties["bore"])
            self.area            = math.pi * (bore / 2) ** 2
            self.stroke          = float(self.properties["stroke"])
            self.spring_k        = float(self.properties["spring_k"])
            self.external_force  = float(self.properties.get("external_force") or 0.0)
            self.friction        = 1e-3   # oculto — valor mínimo para fechar a conta
            stroke_val = float(self.properties["stroke"])
            self.x = stroke_val if default == "extended" else 0.0
            self.flow_var        = f"Q_{self.id}"

            # Batente spring-damper (parâmetros internos, não expostos)
            F_worst = max(abs(self.external_force), self.spring_k * self.stroke, 1.0)
            self.k_end = max(
                self.spring_k * 1e4,
                F_worst / (self.stroke * 1e-6),
                1e8,
            )
            self.c_end = 2.0 * math.sqrt(self.k_end * self.area ** 2 / self.friction)

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
    def is_flow_source(self) -> bool:
        # Mola comprimida pode expulsar oleo — fonte de fluxo variavel.
        return self.x > 0.0

    @property
    def flow_hint(self) -> float:
        # Cilindro nao e fonte de fluxo controlada — q_ref vem da bomba.
        # A semantica de "pode expulsar oleo" e capturada por is_flow_source.
        return 0.0

    @property
    def p_hint(self) -> float:
        F = self.spring_k * self.x + self.external_force
        return F / self.area if self.area > 0 else 0.0

    @property
    def initial_guess(self):
        if self.domain != "hydraulic":
            return {}
        anchor = self.anchors["A"]
        EPS    = self.stroke * 1e-3

        # No batente: o chute físico correto é Q=0, pois o pistão está parado.
        # Usar anchor.pressure aqui é perigoso — quando o circuito troca de
        # topologia (válvula comuta), anchor.pressure ainda carrega a pressão
        # do regime anterior (ex: 1.6 MPa da relief), o que gera Q_eq na casa
        # de +1000 m³/s, 8 ordens de grandeza acima de q_ref, no sinal errado
        # para o bound (Q ≤ 0). O solver leva 30 s para escapar desse chute.
        # Solução: nos batentes, chute direto em 0. Fora dos batentes, usa
        # p_hint da mola (pressão de equilíbrio real), não anchor.pressure.
        if self.x <= EPS or self.x >= self.stroke - EPS:
            return {self.flow_var: 0.0}

        # Zona livre: estima Q pelo equilíbrio de forças usando p_hint
        # (pressão da mola), que é sempre fisicamente consistente — não
        # depende do histórico do NodeContinuity.
        P_eq   = self.p_hint   # F_mola / area — pressão de equilíbrio da mola
        F_mola = self.spring_k * self.x
        F_net  = P_eq * self.area - F_mola - self.external_force
        Q_eq   = (F_net / max(self.friction, 1e-3)) * self.area
        # clipa em ±q_ref para não explodir se F_net for grande por algum motivo
        q_ref  = getattr(self, "q_ref", 1e-4)
        Q_eq   = max(-q_ref, min(q_ref, Q_eq))
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
        v = Q / self.area
        F_hidro = P * self.area
        F_res   = self.spring_k * self.x + self.external_force + self.friction * v
        EPS = self.stroke * 1e-3

        if self.x >= self.stroke - EPS:
            # Complementaridade: ou Q=0 (pistão parado) ou F_net=0 (pistão se move)
            # P_A sempre ancorada pela equação — nunca fica livre no NodeContinuity
            a = -Q / self.q_ref                    # ≥ 0 quando Q ≤ 0
            b = (F_hidro - F_res) / max(F_res, 1)  # ≥ 0 quando pressão sustenta
            return [a + b - math.sqrt(a**2 + b**2)]

        # no batente retraído com força empurrando para fora
        if self.x <= EPS and F_hidro <= F_res:
            F_scale = max(abs(F_res), 1.0)
            return [Q / (self.area * F_scale)]  # força Q → 0

        # zona livre — equilíbrio de forças normal
        F_contact = self._contact_force(self.x, v)
        F_net   = F_hidro - F_res - F_contact
        F_scale = max(abs(F_hidro), abs(F_res), 1.0)
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