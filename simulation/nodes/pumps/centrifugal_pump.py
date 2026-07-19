"""Nó de simulação de bomba centrífuga (domínio hidráulico).

Diferente da bomba de deslocamento fixo (vazão sempre travada em Q_set),
a centrífuga segue uma curva característica contínua relacionando queda
de pressão e vazão -- sem ramificação nenhuma, é uma única equação válida
em qualquer ponto:

    Δp = P_no_P - P_no_S
    Δp = H_shutoff * (1 - (Q_S / Q_max)²)

Em Q_S=0 (bomba afogada, sem vazão): Δp = H_shutoff (pressão de shutoff).
Em Q_S=Q_max (vazão livre, sem carga): Δp = 0.

A parábola só tem solução real pra Δp <= H_shutoff (o máximo, em Q_S=0) --
`bounds` trava Q_S em [0, Q_max] pra que uma contrapressão além do shutoff
resulte em vazão zero (o ponto mais próximo alcançável), não numa vazão
negativa espúria (não haveria raiz real pra encontrar sem esse limite).

Convenção de sinal (node_protocol.py: Q>0 = entrando no componente): S
(sucção, embaixo do sprite) é positivo -- fluido entra ali; P (descarga,
topo) é negativo -- fluido sai ali. Mesma convenção, mesmas portas e
mesmo sprite (só o desenho do círculo muda) da FixedDisplacementPump.

Ao contrário de lá, os nomes das variáveis aqui já nascem ligados
diretamente ao nome da porta (flow_var_p, flow_var_s) -- não "in"/"out",
que só causou confusão sem necessidade no irmão desta classe.
"""

from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin


class CentrifugalPump(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "centrifugal_pump", domain=domain, properties=properties)

        if self.domain == "hydraulic":
            h_shutoff = self.properties.get("H_shutoff")
            if h_shutoff is None:
                raise ValueError(
                    f"CentrifugalPump '{self.id}': propriedade obrigatória 'H_shutoff' não preenchida."
                )
            q_max = self.properties.get("Q_max")
            if q_max is None:
                raise ValueError(
                    f"CentrifugalPump '{self.id}': propriedade obrigatória 'Q_max' não preenchida."
                )
            self.H_shutoff = float(h_shutoff)
            self.Q_max = float(q_max)
            self.flow_var_p = f"Q_{self.id}_P"
            self.flow_var_s = f"Q_{self.id}_S"

    @property
    def is_flow_source(self) -> bool:
        return True

    @property
    def flow_hint(self) -> float:
        return self.Q_max

    @property
    def p_hint(self) -> float:
        return self.H_shutoff

    @property
    def variables(self):
        return [self.flow_var_p, self.flow_var_s]

    @property
    def bounds(self):
        # A curva Δp=H_shutoff*(1-(Q_S/Q_max)²) só tem solução real pra
        # Δp <= H_shutoff (o máximo da parábola, em Q_S=0) -- sem limites,
        # uma contrapressão além do shutoff não tem raiz nenhuma, e o
        # solver pode escorregar pra vazão negativa tentando achar uma.
        # Limitando ao envelope de operação válido (0 <= Q_S <= Q_max), o
        # ponto mais próximo alcançável quando a contrapressão excede o
        # shutoff fica em Q_S=0 -- vazão trava em zero, que é o
        # comportamento físico esperado (a bomba não vence a
        # contrapressão, não passa a girar em reverso sozinha).
        return {
            self.flow_var_s: (0.0, self.Q_max),
            self.flow_var_p: (-self.Q_max, 0.0),
        }

    @property
    def initial_guess(self):
        return {
            self.flow_var_p: -self.Q_max / 2,
            self.flow_var_s:  self.Q_max / 2,
        }

    def hydraulic_ports(self):
        return {
            "P": self.flow_var_p,
            "S": self.flow_var_s,
        }

    def equations(self, x, idx):
        Q_p = x[idx[self.flow_var_p]]
        Q_s = x[idx[self.flow_var_s]]

        P_p = x[idx[self.anchors["P"].pressure_var]]
        P_s = x[idx[self.anchors["S"].pressure_var]]

        Q_scale = max(self.q_ref, 1e-12)
        P_scale = max(self.p_ref, 1e-3)

        delta_p = P_p - P_s
        curve = self.H_shutoff * (1 - (Q_s / self.Q_max) ** 2)

        eq_conservation = (Q_p + Q_s) / Q_scale
        eq_curve = (delta_p - curve) / P_scale

        return [eq_conservation, eq_curve]
