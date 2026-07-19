"""Simulation node for the throttle check valve (pneumatic and hydraulic).

Behaviour (pneumatic)
----------------------
The valve exposes two anchors X (left) and Y (right).  State propagation
is handled entirely by the engine through get_internal_connections().

Free-flow direction (Y=1, X=0):
    Connects X↔Y immediately.

Restricted direction (X=1, Y=0):
    Connects X↔Y after `delay_steps` simulation steps.

Same state (X=Y):
    Disconnects X↔Y, holds last sprite state.

All decisions — connection, counter, and sprite latch — are made in
post_step_update(), which sees the fully stabilised anchor states.
update() only exposes the current _open flag to get_internal_connections().

Visual state (latched in post_step_update):
    "open"   — last stabilised direction was free-flow  (Y=1, X=0)
    "closed" — last stabilised direction was restricted  (X=1, Y=0)
    Default: "open"

`delay_steps` is read from ``properties["delay_steps"]`` (default: 3).
`delay_steps` só é usado no domínio pneumático.

Behaviour (hydraulic)
-----------------------
Um "one-way flow control valve" de verdade: caminho de retenção livre em
paralelo com um orifício fixo -- diferente da válvula de retenção pura
(simulation/nodes/check_valve/check_valve.py), o sentido restrito NUNCA
bloqueia, só resiste. É por isso que o pneumático usa um atraso
(`delay_steps`) em vez de bloquear: o atraso aproxima, no domínio
booleano, o tempo que um fluxo resistido levaria pra pressurizar o lado
de baixo -- no hidráulico não precisa de atraso nenhum, a equação de
orifício já dá a relação contínua ΔP–Q direto.

    b = P_X - P_Y

    Q_Y >= 0  (Y empurra, sentido favorável):
        resistência zero -- P_X = P_Y, igual ao ramo aberto da retenção
        pura (check_valve.py).

    Q_Y < 0  (sentido restrito):
        NÃO bloqueia -- passa pelo orifício fixo (condutância `k`):
        b = copysign((Q_Y / k)², -Q_Y)
        (mesma equação de orifício turbulento que Valve_3_2_Ways usa;
        o sinal amarrado a -Q_Y garante que o fluxo seja negativo em Y
        -- saindo por Y, entrando por X -- nesse ramo).

A ramificação usa o sinal de Q_Y -- não o de P_X-P_Y -- de propósito:
P_X/P_Y são as próprias incógnitas deste solve, então ramificar por elas
é circular. O ramo favorável não menciona Q_Y em nenhuma equação, então
se a ramificação fosse por pressão, P_X=P_Y=0 satisfaria o ramo
"favorável" mesmo com um Q_Y claramente do sentido restrito (imposto de
fora, por uma bomba de vazão fixa por exemplo) -- uma raiz espúria onde
a pressão nunca sobe pra vencer o orifício. Q_Y já vem determinado pela
conservação + o que estiver ligado à válvula, então ramificar por ele
elimina essa ambiguidade.

Diferente da retenção pura, isso NÃO é complementaridade (nunca força
vazão ou pressão exatamente a zero) -- é uma resistência que muda de
valor conforme o sentido, então usa uma ramificação dura (if/else, igual
ao já usado em DirectOperatedReliefValve) em vez de Fischer-Burmeister.

`k` é obrigatório no domínio hidráulico (mesmo padrão de Valve_3_2_Ways).
Mais a conservação de vazão: Q_X + Q_Y = 0.

Visual state (ver get_visual_state):
    "open"   -- b <= 0 (sentido favorável, sem resistência)
    "closed" -- b > 0 (sentido restrito, passando pelo orifício)
"""

from __future__ import annotations

import math

from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin

_DEFAULT_DELAY = 3


class ThrottleCheckValve(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(
            node_id, "throttle_check_valve", domain=domain, properties=properties
        )

        if self.domain == "hydraulic":
            k = self.properties.get("k")
            if k is None:
                raise ValueError(
                    f"ThrottleCheckValve '{self.id}': propriedade obrigatória 'k' não preenchida."
                )
            self.k = float(k)
            self.flow_var_x = f"Q_{self.id}_X"
            self.flow_var_y = f"Q_{self.id}_Y"
        else:
            self._delay_steps: int = int(
                (self.properties or {}).get("delay_steps", _DEFAULT_DELAY)
            )

            # 0 = idle. >0 = counting down.
            self._steps_remaining: int = 0

            # Whether the valve is open (X ↔ Y connected).
            self._open: bool = False

            # Latched sprite — only updated in post_step_update on stabilised states.
            self._sprite: str = "open"

    # ------------------------------------------------------------------
    # Domínio pneumático
    # ------------------------------------------------------------------

    def update(self, outputs=None):
        """Expose _open to the engine — no decisions made here."""
        pass

    def post_step_update(self, dt=None):
        """All logic runs here on fully stabilised anchor states."""
        if self.domain != "pneumatic":
            return
        super().post_step_update(dt=dt)

        x = self.anchors["X"].state
        y = self.anchors["Y"].state

        if x == y:
            # Same state — disconnect, hold sprite.
            self._open = False
            self._steps_remaining = 0
            return

        if y and not x:
            # Free-flow — connect immediately, latch sprite open.
            self._open = True
            self._sprite = "open"
            self._steps_remaining = 0
            return

        # x and not y — restricted direction.
        self._sprite = "closed"

        if self._open:
            # Already open from a previous step — stay open.
            return

        if self._steps_remaining == 0:
            self._steps_remaining = self._delay_steps

        self._steps_remaining -= 1

        if self._steps_remaining <= 0:
            self._steps_remaining = 0
            self._open = True

    def get_internal_connections(self):
        if self.domain != "pneumatic":
            return []
        if self._open:
            return [("X", "Y")]
        return []

    def get_visual_state(self) -> str:
        if self.domain == "hydraulic":
            p_x = self.anchors["X"].pressure
            p_y = self.anchors["Y"].pressure
            if isinstance(p_x, (int, float)) and isinstance(p_y, (int, float)):
                return "closed" if (p_x - p_y) > 0 else "open"
            return "open"
        return self._sprite

    # ------------------------------------------------------------------
    # Undo / history (pneumático apenas -- hidráulico não tem estado
    # próprio, tudo decidido a cada solve pelas equações)
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        state = super().get_state()
        if self.domain == "pneumatic":
            state["steps_remaining"] = self._steps_remaining
            state["open"] = self._open
            state["sprite"] = self._sprite
        return state

    def set_state(self, state: dict):
        super().set_state(state)
        if self.domain != "pneumatic":
            return
        self._steps_remaining = state.get("steps_remaining", 0)
        self._open = state.get("open", False)
        self._sprite = state.get("sprite", "open")
        self._delay_steps = int(
            (self.properties or {}).get("delay_steps", _DEFAULT_DELAY)
        )

    # ------------------------------------------------------------------
    # Domínio hidráulico
    # ------------------------------------------------------------------

    @property
    def variables(self):
        if self.domain != "hydraulic":
            return []
        vars_ = [self.flow_var_x, self.flow_var_y]
        for anchor_name in self.hydraulic_ports().keys():
            anchor = self.anchors.get(anchor_name)
            if anchor and anchor.pressure_var:
                vars_.append(anchor.pressure_var)
        return vars_

    def hydraulic_ports(self):
        if self.domain != "hydraulic":
            return {}
        return {"X": self.flow_var_x, "Y": self.flow_var_y}

    @property
    def initial_guess(self):
        if self.domain != "hydraulic":
            return {}
        return {self.flow_var_x: -1.0, self.flow_var_y: 1.0}

    def equations(self, x, idx):
        Q_x = x[idx[self.flow_var_x]]
        Q_y = x[idx[self.flow_var_y]]
        P_x = x[idx[self.anchors["X"].pressure_var]]
        P_y = x[idx[self.anchors["Y"].pressure_var]]

        Q_scale = max(self.q_ref, 1e-12)
        P_scale = max(self.p_ref, 1e-3)

        eq_conservation = (Q_x + Q_y) / Q_scale

        # A ramificação usa o sinal de Q_y -- imposto de fora pelo resto do
        # circuito (ex: uma bomba de vazão fixa) -- e não o de P_X - P_Y.
        # Ramificar por pressão seria circular: P_X/P_Y são as próprias
        # incógnitas que este solve está resolvendo, então o ramo "favorável"
        # (que não menciona Q_y) pode ser satisfeito por P_X=P_Y=0 mesmo
        # quando Q_y é claramente o do sentido restrito (forçado de fora),
        # já que nada naquele ramo valida a direção real do fluxo -- uma
        # raiz espúria. Ramificando por Q_y (que já vem determinado pela
        # conservação + o que estiver ligado à válvula) elimina essa
        # ambiguidade.
        b = P_x - P_y
        if Q_y >= 0:
            # Sentido favorável -- resistência zero, mesmo ramo da
            # retenção pura quando aberta.
            eq_valve = (P_x - P_y) / P_scale
        else:
            # Sentido restrito -- não bloqueia, passa pelo orifício fixo.
            eq_valve = (b - math.copysign((Q_y / self.k) ** 2, -Q_y)) / P_scale

        return [eq_conservation, eq_valve]
