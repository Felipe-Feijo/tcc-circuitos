"""
simulation/hydraulic/scale_context.py

Contexto de escala para o domínio hidráulico.

ScaleContext
    Objeto imutável montado uma vez por solve. Carrega p_ref, q_ref
    e o zc calculado pelo ZcScheduler. Passado para NodeContinuity
    e para todos os nós via set_scale().

ZcScheduler
    Calcula o zc (impedância do capacitor virtual de pressurização)
    em função da iteração atual. O zc cresce uma década a cada `tau`
    iterações, ancorado em p_ref/q_ref, com teto em zc_max.

ScaleManager
    Estima p_ref e q_ref a partir dos hints dos nós, com memória
    da última escala válida para sobreviver a transições.

Faixa de operação alvo: 50–300 bar (5e6–3e7 Pa)
Vazões típicas: 5–50 L/min (8e-5–8e-4 m³/s)
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Defaults para a faixa hidráulica industrial (50–300 bar)
# ---------------------------------------------------------------------------

#: Pressão de referência default em Pa (≈ 100 bar)
DEFAULT_P_REF: float = 100 * 1e5

#: Vazão de referência default em m³/s (≈ 20 L/min)
DEFAULT_Q_REF: float = 20 / 60_000

#: Ganho base do zc: p_ref/q_ref × ZC_BASE_FACTOR
#: Fator 10 posiciona o capacitor virtual como "moderadamente rígido"
ZC_BASE_FACTOR: float = 10.0

#: Número de iterações para subir uma década no zc
ZC_TAU: float = 3.0

#: Teto do zc em múltiplos do zc_base (4 décadas)
ZC_MAX_DECADES: float = 4.0


# ---------------------------------------------------------------------------
# ScaleContext
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScaleContext:
    """
    Contexto de escala imutável para um solve específico.

    Criado pelo engine via ScaleManager.build_context() antes de
    cada chamada ao solver. Distribuído para NodeContinuity e nós.

    Atributos
    ---------
    p_ref : pressão de referência em Pa
    q_ref : vazão de referência em m³/s
    zc    : impedância do capacitor virtual em Pa·s/m³
    """
    p_ref: float
    q_ref: float
    zc: float

    def __post_init__(self):
        assert self.p_ref > 0, f"p_ref deve ser positivo, got {self.p_ref}"
        assert self.q_ref > 0, f"q_ref deve ser positivo, got {self.q_ref}"
        assert self.zc > 0,    f"zc deve ser positivo, got {self.zc}"

    def __repr__(self) -> str:
        return (
            f"ScaleContext("
            f"p_ref={self.p_ref:.2e} Pa, "
            f"q_ref={self.q_ref:.2e} m³/s, "
            f"zc={self.zc:.2e} Pa·s/m³)"
        )


# ---------------------------------------------------------------------------
# ZcScheduler
# ---------------------------------------------------------------------------

class ZcScheduler:
    """
    Calcula o zc em função da iteração atual.

    Crescimento: zc(iter) = zc_base × 10^(iter / tau)
    Teto:        zc_max   = zc_base × 10^(ZC_MAX_DECADES)

    O zc_base é ancorado em p_ref/q_ref × ZC_BASE_FACTOR, garantindo
    que o capacitor virtual opera na mesma escala do circuito real.

    Por que crescer por iteração?
    ------------------------------
    Se o circuito não convergiu (ex: relief ainda fechada mas deveria
    abrir), a pressão precisa subir o suficiente para mudar o estado
    de algum componente. O zc crescente aumenta progressivamente a
    "rigidez" da acumulância, forçando a pressão a subir até que a
    topologia mude. O teto de 4 décadas evita explosão numérica.

    Parâmetros
    ----------
    tau           : iterações por década de zc (default: 3)
    base_factor   : multiplicador sobre p_ref/q_ref (default: ZC_BASE_FACTOR)
    max_decades   : teto em décadas acima do base (default: ZC_MAX_DECADES)
    """

    def __init__(
        self,
        tau: float = ZC_TAU,
        base_factor: float = ZC_BASE_FACTOR,
        max_decades: float = ZC_MAX_DECADES,
    ):
        self.tau = tau
        self.base_factor = base_factor
        self.max_decades = max_decades

    def zc_base(self, p_ref: float, q_ref: float) -> float:
        """zc na iteração 0, ancorado na escala do circuito."""
        return (p_ref / q_ref) * self.base_factor

    def zc_at(self, iteration: int, p_ref: float, q_ref: float) -> float:
        """
        zc para a iteração dada.

        Nunca desce abaixo de zc_base nem sobe acima de
        zc_base × 10^max_decades.
        """
        base = self.zc_base(p_ref, q_ref)
        gain = 10 ** (iteration / self.tau)
        cap  = 10 ** self.max_decades
        return base * min(gain, cap)


# ---------------------------------------------------------------------------
# ScaleManager
# ---------------------------------------------------------------------------

class ScaleManager:
    """
    Estima p_ref e q_ref a partir dos hints dos nós hidráulicos.

    Estratégia em cascata para p_ref:
      1. max dos p_hint dos nós (se algum > 1 Pa)
      2. inferência via atributo `pressure` (Reservoir com P > 0)
      3. memória da última escala válida
      4. fallback absoluto: DEFAULT_P_REF

    Estratégia em cascata para q_ref:
      1. max dos flow_hint dos nós (se algum > 1e-10)
      2. memória da última escala válida
      3. fallback absoluto: DEFAULT_Q_REF

    A memória é essencial para transições de topologia: quando uma
    válvula comuta ou um cilindro trava, os hints podem cair a zero
    por um frame. Sem memória, o scaling colapsa exatamente na
    iteração mais crítica.
    """

    def __init__(self):
        self._last_p: float = DEFAULT_P_REF
        self._last_q: float = DEFAULT_Q_REF

    def estimate(self, nodes: list) -> tuple[float, float]:
        """
        Retorna (p_ref, q_ref) em Pa e m³/s.

        Atualiza a memória interna se os valores estimados são válidos.
        """
        p_ref = self._estimate_pressure(nodes)
        q_ref = self._estimate_flow(nodes)

        # atualiza memória só quando temos valores confiáveis
        if p_ref > 1.0:
            self._last_p = p_ref
        if q_ref > 1e-10:
            self._last_q = q_ref

        return p_ref, q_ref

    def build_context(
        self,
        nodes: list,
        iteration: int,
        scheduler: ZcScheduler | None = None,
    ) -> ScaleContext:
        """
        Monta um ScaleContext completo para o solve atual.

        Parâmetros
        ----------
        nodes     : lista de HydraulicNode do circuito
        iteration : iteração atual do loop de convergência hidráulica
        scheduler : ZcScheduler customizado (usa default se None)
        """
        if scheduler is None:
            scheduler = ZcScheduler()

        p_ref, q_ref = self.estimate(nodes)
        zc = scheduler.zc_at(iteration, p_ref, q_ref)

        return ScaleContext(p_ref=p_ref, q_ref=q_ref, zc=zc)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _estimate_pressure(self, nodes: list) -> float:
        # 1. hints explícitos dos nós
        hints = [
            n.p_hint for n in nodes
            if hasattr(n, "p_hint") and isinstance(n.p_hint, (int, float))
            and n.p_hint > 1.0
        ]
        if hints:
            return max(hints)

        # 2. inferência via Reservoir ou nó com pressão fixada
        inferred = [
            n.pressure for n in nodes
            if hasattr(n, "pressure")
            and isinstance(n.pressure, (int, float))
            and n.pressure > 1.0
        ]
        if inferred:
            return max(inferred)

        # 3. memória
        return self._last_p

    def _estimate_flow(self, nodes: list) -> float:
        hints = [
            n.flow_hint for n in nodes
            if hasattr(n, "flow_hint") and isinstance(n.flow_hint, (int, float))
            and n.flow_hint > 1e-10
        ]
        if hints:
            return max(hints)

        # memória
        return self._last_q