"""Nó de simulação de motor hidráulico de deslocamento fixo.

Inverso mecânico da FixedDisplacementPump: em vez de converter rotação em
vazão/pressão, converte vazão/pressão recebidas em rotação/torque no eixo.

    Q = D · ω      (vazão proporcional à velocidade angular)
    T = D · Δp     (torque proporcional à queda de pressão)

Sentido de projeto: A (topo, pra onde o triângulo do sprite aponta) é a
entrada de referência; B (base) é a saída de referência. Δp = P_A - P_B.
Positivo em Q_A e em Δp = operação no sentido de projeto (bate com a seta
do sprite).

Reversão de sentido não precisa de tratamento especial nenhum: a equação
do motor nunca depende do SINAL de Q_A, só o resto do circuito
(conservação) decide -- se o circuito empurrar vazão ao contrário, Q_A
(e portanto ω=Q_A/D) sai negativo naturalmente, sem ramificação nem
risco de raiz espúria (mesmo cuidado que levou à correção da válvula
estranguladora).

Dois modos de operação (properties["control_mode"]), mutuamente
exclusivos -- cada um define qual das duas propriedades (T_load ou
omega_target) é obrigatória:

    "torque": properties["T_load"] (N·m) -- carga de torque CONSTANTE,
        imposta independente do sentido de rotação (não é atrito -- um
        atrito de verdade sempre se opõe ao sentido de ω, o que exigiria
        sinal(Q) e reintroduziria o mesmo tipo de ramificação evitado
        aqui). Equação: Δp = T_load / D.
        ω = Q_A/D sai derivado (calculado no lado gráfico a partir do
        fluxo resolvido, mesmo esquema da velocidade do pistão).

    "speed": properties["omega_target"] (rad/s) -- velocidade alvo
        imposta, como um servo. Equação: Q_A = D · omega_target (vazão
        travada, mesma ideia da FixedDisplacementPump).
        T = Δp · D sai derivado (calculado no lado gráfico a partir da
        pressão resolvida).

`D` é sempre obrigatório. Só um dos dois campos (T_load / omega_target)
é obrigatório, conforme control_mode.
"""

from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin


class FixedDisplacementMotor(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "fixed_displacement_motor", domain=domain, properties=properties)

        if self.domain == "hydraulic":
            d = self.properties.get("D")
            if d is None:
                raise ValueError(
                    f"FixedDisplacementMotor '{self.id}': propriedade obrigatória 'D' não preenchida."
                )
            self.D = float(d)

            self.control_mode = self.properties.get("control_mode", "torque")
            if self.control_mode not in ("torque", "speed"):
                raise ValueError(
                    f"FixedDisplacementMotor '{self.id}': 'control_mode' deve ser 'torque' ou 'speed', "
                    f"recebeu {self.control_mode!r}."
                )

            if self.control_mode == "torque":
                t_load = self.properties.get("T_load")
                if t_load is None:
                    raise ValueError(
                        f"FixedDisplacementMotor '{self.id}': propriedade obrigatória 'T_load' "
                        "não preenchida (control_mode='torque')."
                    )
                self.T_load = float(t_load)
            else:
                omega_target = self.properties.get("omega_target")
                if omega_target is None:
                    raise ValueError(
                        f"FixedDisplacementMotor '{self.id}': propriedade obrigatória 'omega_target' "
                        "não preenchida (control_mode='speed')."
                    )
                self.omega_target = float(omega_target)

            self.flow_var_a = f"Q_{self.id}_A"
            self.flow_var_b = f"Q_{self.id}_B"

    @property
    def is_flow_source(self) -> bool:
        return True

    @property
    def flow_hint(self) -> float:
        if self.control_mode == "speed":
            return abs(self.D * self.omega_target)
        return 0.0

    @property
    def p_hint(self) -> float:
        if self.control_mode == "torque":
            return abs(self.T_load / self.D)
        return 0.0

    @property
    def variables(self):
        vars_ = [self.flow_var_a, self.flow_var_b]
        for anchor_name in self.hydraulic_ports().keys():
            anchor = self.anchors.get(anchor_name)
            if anchor and anchor.pressure_var:
                vars_.append(anchor.pressure_var)
        return vars_

    @property
    def initial_guess(self):
        if self.control_mode == "speed":
            q = self.D * self.omega_target
            return {self.flow_var_a: q, self.flow_var_b: -q}
        return {self.flow_var_a: 1.0, self.flow_var_b: -1.0}

    def hydraulic_ports(self):
        return {
            "A": self.flow_var_a,
            "B": self.flow_var_b,
        }

    def equations(self, x, idx):
        Q_a = x[idx[self.flow_var_a]]
        Q_b = x[idx[self.flow_var_b]]

        Q_scale = max(self.q_ref, 1e-12)
        P_scale = max(self.p_ref, 1e-3)

        eq_conservation = (Q_a + Q_b) / Q_scale

        if self.control_mode == "torque":
            P_a = x[idx[self.anchors["A"].pressure_var]]
            P_b = x[idx[self.anchors["B"].pressure_var]]
            delta_p = P_a - P_b
            eq_mode = (delta_p - self.T_load / self.D) / P_scale
        else:
            eq_mode = (Q_a - self.D * self.omega_target) / Q_scale

        return [eq_conservation, eq_mode]
