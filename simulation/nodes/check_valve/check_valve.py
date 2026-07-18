"""Simulation node for the check valve (pneumatic and hydraulic).

Behaviour (pneumatic)
----------------------
The valve exposes two anchors X (left) and Y (right), and optionally a
third anchor Z (pilot), present only when properties["piloted"] is True.

Two very different mechanisms are at play, depending on whether the
pilot is currently forcing the valve open:

1. Normal check function (Z not forcing, decided purely by Y):
   X does NOT get merged with Y via get_internal_connections() -- see
   below for why. Instead X acts as its own pressure driver
   (anchor.is_driver = True, exactly like PressureSource/Exhaust do for
   their own anchors in simulation/nodes/nodes.py) ONLY WHILE Y=1, and
   is only ever pushed to state=True, never back to False by this node.
   The moment Y drops, X.is_driver goes back to False -- X becomes an
   ordinary follower again. This matters: if X stayed a driver forever,
   SimulationEngine's group algorithm would never update X's OWN state
   again (drivers are never overwritten by _update_pneumatic_domain), so
   X would keep reporting a stale True even after a real exhaust
   downstream vented the rest of its group to False. As a plain
   follower, X correctly freezes (no driver anywhere in its group --
   trapped pressure held) or correctly follows a real driver (exhaust or
   new source) that's actually there.

   A symmetric union of X and Y (the mechanism get_internal_connections()
   normally triggers via SimulationEngine._get_connected_group()) has no
   direction: once merged, ANY driver reachable from either side
   (including an exhaust that later reaches Y when an upstream
   directional valve switches from supply to exhaust) forces the WHOLE
   merged group down, leaking pressure backwards through what should be
   a closed valve. A real check valve must never do that in this mode --
   once pressure passes through, it stays trapped on the X side even
   after Y is vented, until something downstream of X actively vents it.

   This is also why there's no one-step propagation lag here (unlike the
   old get_internal_connections-based design this replaced): update()
   runs every fixed-point iteration (before the domain is resolved for
   that iteration), so X latches to True within the same simulation step
   Y turns 1 in.

2. Pilot-forced-open (properties["piloted"] is True and Z=1): the pilot
   mechanically holds the poppet away from its seat -- the valve becomes
   a plain, direction-less open passage, exactly like an ordinary open
   valve or a piece of pipe. This is the intentional use case for a
   pilot-operated check valve: releasing pressure that would otherwise be
   trapped (e.g. unlocking a load-holding cylinder). So while forced
   open, X stops being an artificial driver (is_driver = False) and
   get_internal_connections() DOES return [("X", "Y")] -- the ordinary
   symmetric union takes over, and whatever real drivers exist on either
   side (a source, an exhaust, or none) decide the merged group's state
   exactly like any other passive two-port component.

Free-flow (Y=1, independente de X, sem pilotagem forçando): latches X to
True (modo 1).
Blocked (Y=0, sem pilotagem forçando): não faz nada -- X mantém o que já
tinha (pressão retida, não recua).
Pilotagem (Z=1, só quando properties["piloted"] é True): une X e Y
simetricamente (modo 2) -- deixa de ser um diodo, vira passagem aberta.

Behaviour (hydraulic)
-----------------------
Mais simples que o pneumático: nenhum estado próprio, tudo decidido a
cada solve pelas equações. Modela a válvula via complementaridade
suavizada (Fischer-Burmeister), o mesmo mecanismo já usado por
DirectOperatedReliefValve (simulation/nodes/relief_valve.py) para
alternar entre dois regimes sem uma transição abrupta que quebre a
convergência do solver:

    a = Q_Y / Q_scale                (quer a >= 0)
    b = (P_X - P_Y) / P_scale        (quer b >= 0)
    eq_fb = a + b - sqrt(a² + b²)    (== 0  =>  a>=0, b>=0, a*b=0)

`b = P_X - P_Y` é a "contrapressão de vedação": quando X (a jusante) está
mais pressurizado que Y (a montante), b>=0 e a esfera é empurrada contra
o assento -- bloqueada (a=0, Q_Y=0), mas P_X pode exceder P_Y à vontade
(selada). Quando Y consegue empurrar a esfera (fluxo favorável), b=0
(sem queda de pressão, P_X=P_Y) e a=Q_Y>=0 fica livre.

Ou seja: OU a válvula está fechada (Q_Y = 0, com P_X podendo ficar acima
de P_Y à vontade -- selada), OU está aberta com queda de pressão zero
(P_Y = P_X, Q_Y >= 0 livre) -- nunca as duas coisas ao mesmo tempo.
Mais a conservação de vazão (sem acúmulo interno):

    Q_X + Q_Y = 0

Pilotagem (properties["piloted"] é True e a pressão em Z >= 1 bar):
substitui a complementaridade por uma equação de queda de pressão zero
incondicional (P_X = P_Y) -- o piloto mecanicamente afasta a esfera do
assento, e a válvula vira uma passagem aberta nos dois sentidos, sem
nenhuma restrição de sentido. Abaixo de 1 bar no piloto, comporta-se
exatamente como a versão não pilotada.

A âncora Z, quando presente, é modelada como uma porta "morta": vazão
sempre zero (Q_Z = 0, um sensor de pressão, não uma porta de fluxo real)
-- ela só precisa de uma equação própria pra fechar o sistema (dar ao
solver uma equação para a variável Q_Z que só esta válvula usa); a
pressão em Z continua livre, determinada pelo resto do circuito ligado
a ela por fio.

Ao contrário das válvulas direcionais hidráulicas (Valve_3_2_Ways), não
há nenhuma propriedade obrigatória tipo "k" -- a retenção não modela
nenhuma resistência/orifício, só a restrição de sentido.

Visual state (ver get_visual_state):
    "open"   -- Y=1/Q_Y>0 ou pilotagem forçando
    "closed" -- caso contrário
"""

from __future__ import annotations

import math

from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin

_PILOT_PRESSURE_THRESHOLD = 1e5  # 1 bar, em Pa


class CheckValve(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "check_valve", domain=domain, properties=properties)

        if self.domain == "hydraulic":
            self._piloted_hydraulic = bool((self.properties or {}).get("piloted", False))
            self.flow_var_x = f"Q_{self.id}_X"
            self.flow_var_y = f"Q_{self.id}_Y"
            if self._piloted_hydraulic:
                self.flow_var_z = f"Q_{self.id}_Z"

    # ------------------------------------------------------------------
    # Domínio pneumático
    # ------------------------------------------------------------------

    def _piloted_open(self) -> bool:
        piloted = (self.properties or {}).get("piloted", False)
        return bool(piloted and "Z" in self.anchors and self.anchors["Z"].state)

    def update(self, outputs=None):
        if self.domain != "pneumatic":
            return

        x_anchor = self.anchors["X"]

        if self._piloted_open():
            # Passagem aberta simétrica -- get_internal_connections() é
            # quem une X e Y agora; X não deve fingir ser driver aqui,
            # senão contamina o grupo com um valor artificial em vez de
            # deixar os drivers reais (dos dois lados) decidirem.
            x_anchor.is_driver = False
            return

        if self.anchors["Y"].state:
            x_anchor.is_driver = True
            x_anchor.state = True
        else:
            x_anchor.is_driver = False

    def get_internal_connections(self):
        if self._piloted_open():
            return [("X", "Y")]
        return []

    def get_visual_state(self) -> str:
        if self.domain == "hydraulic":
            y_flow = self.anchors["Y"].flow
            flowing = isinstance(y_flow, (int, float)) and y_flow > 0
            return "open" if (flowing or self._piloted_open_hydraulic()) else "closed"

        y = self.anchors["Y"].state
        return "open" if (y or self._piloted_open()) else "closed"

    # ------------------------------------------------------------------
    # Domínio hidráulico
    # ------------------------------------------------------------------

    def _piloted_open_hydraulic(self) -> bool:
        if not self._piloted_hydraulic:
            return False
        p_z = self.anchors["Z"].pressure
        return isinstance(p_z, (int, float)) and p_z >= _PILOT_PRESSURE_THRESHOLD

    @property
    def variables(self):
        if self.domain != "hydraulic":
            return []
        vars_ = [self.flow_var_x, self.flow_var_y]
        if self._piloted_hydraulic:
            vars_.append(self.flow_var_z)
        for anchor_name in self.hydraulic_ports().keys():
            anchor = self.anchors.get(anchor_name)
            if anchor and anchor.pressure_var:
                vars_.append(anchor.pressure_var)
        return vars_

    def hydraulic_ports(self):
        if self.domain != "hydraulic":
            return {}
        ports = {"X": self.flow_var_x, "Y": self.flow_var_y}
        if self._piloted_hydraulic:
            ports["Z"] = self.flow_var_z
        return ports

    @property
    def bounds(self):
        if self.domain != "hydraulic" or self._piloted_hydraulic:
            # Pilotada: pode operar em modo retenção OU passagem livre
            # (nos dois sentidos) dependendo da pressão do piloto,
            # avaliada dentro de equations() -- travar Q_Y/Q_X num
            # sentido só quebraria o modo livre. Sem bounds aqui, quem
            # decide é a própria equação.
            return {}
        return {
            self.flow_var_y: (0.0, None),   # Q_Y nunca negativo
            self.flow_var_x: (None, 0.0),   # Q_X nunca positivo
        }

    @property
    def initial_guess(self):
        if self.domain != "hydraulic":
            return {}
        guess = {
            self.flow_var_x: -1.0,
            self.flow_var_y: 1.0,
        }
        if self._piloted_hydraulic:
            guess[self.flow_var_z] = 0.0
        return guess

    def equations(self, x, idx):
        Q_x = x[idx[self.flow_var_x]]
        Q_y = x[idx[self.flow_var_y]]
        P_x = x[idx[self.anchors["X"].pressure_var]]
        P_y = x[idx[self.anchors["Y"].pressure_var]]

        Q_scale = max(self.q_ref, 1e-12)
        P_scale = max(self.p_ref, 1e-3)

        eq_conservation = (Q_x + Q_y) / Q_scale

        piloted_open = False
        eqs_extra = []
        if self._piloted_hydraulic:
            Q_z = x[idx[self.flow_var_z]]
            eqs_extra.append(Q_z / Q_scale)  # porta morta -- só sensoriamento

            P_z = x[idx[self.anchors["Z"].pressure_var]]
            piloted_open = P_z >= _PILOT_PRESSURE_THRESHOLD

        if piloted_open:
            eq_dp = (P_x - P_y) / P_scale
            return [eq_conservation, eq_dp] + eqs_extra

        a = Q_y / Q_scale
        b = (P_x - P_y) / P_scale
        eq_fb = a + b - math.sqrt(a * a + b * b)
        return [eq_conservation, eq_fb] + eqs_extra
