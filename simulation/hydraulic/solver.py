"""
simulation/hydraulic/solver.py

Solver não-linear para circuitos hidráulicos.

Conteúdo
--------
NodeContinuity        : equação de acumulância por nó de pressão
NonlinearSystemSolver : monta e resolve o sistema de equações

Este módulo substitui simulation/hydraulic_solver.py (removido).
"""

from __future__ import annotations

import math
import numpy as np
from scipy.optimize import fsolve, least_squares

from simulation.hydraulic.scale_context import ScaleContext


# ---------------------------------------------------------------------------
# NodeContinuity — capacitor virtual de pressurização
# ---------------------------------------------------------------------------

class NodeContinuity:
    """
    Equação de acumulância para um nó de pressão.

    Modela um capacitor hidráulico virtual que equilibra desequilíbrios
    de vazão acumulando pressão. Serve dois propósitos:

      1. Numérico: fecha o sistema de equações (um nó de pressão não
         conectado a um source precisaria de uma equação extra).

      2. Pressurização: se o circuito não converge (ex: relief fechada
         mas deveria abrir), o zc crescente força a pressão a subir
         até que a topologia mude — veja ZcScheduler.

    Equação:
        Q_sum - (P - P_prev) / zc = 0

    Onde:
        Q_sum  = soma algébrica das vazões no nó (positivo = entrando)
        P      = pressão atual no nó
        P_prev = pressão da iteração anterior (memória)
        zc     = impedância do capacitor [Pa·s/m³]

    Parâmetros
    ----------
    pressure_var : nome da variável de pressão do nó
    flow_vars    : lista de nomes das variáveis de vazão conectadas
    """

    def __init__(self, pressure_var: str, flow_vars: list[str]):
        self.pressure_var = pressure_var
        self.flow_vars = flow_vars

        self.p_previous: float = 0.0
        self._ctx: ScaleContext | None = None

    @property
    def variables(self) -> list[str]:
        return [self.pressure_var]

    @property
    def bounds(self) -> dict[str, tuple[float | None, float | None]]:
        return {self.pressure_var: (0.0, None)}  # pressão nunca negativa

    def apply_context(self, ctx: ScaleContext) -> None:
        """Recebe o ScaleContext antes de cada solve."""
        self._ctx = ctx

    def equations(self, x: np.ndarray, idx: dict[str, int]) -> list[float]:
        assert self._ctx is not None, "apply_context() não foi chamado antes de equations()"
        P     = x[idx[self.pressure_var]]
        Q_sum = -sum(x[idx[q]] for q in self.flow_vars if q in idx)
        # normalizado por q_ref para manter equação adimensional
        return [(Q_sum - (P - self.p_previous) / self._ctx.zc) / self._ctx.q_ref]

    def update_pressure(self, sol: dict[str, float]) -> None:
        """
        Atualiza P_prev após um solve bem-sucedido.
        Valores de ruído numérico são descartados.
        """
        if self.pressure_var not in sol:
            return
        new_p = sol[self.pressure_var]
        assert self._ctx is not None
        noise_threshold = self._ctx.q_ref * self._ctx.zc * 1e-6
        self.p_previous = 0.0 if new_p < noise_threshold else new_p

    def reset(self) -> None:
        """Zera a memória de pressão (mudança de topologia)."""
        self.p_previous = 0.0


# ---------------------------------------------------------------------------
# NonlinearSystemSolver
# ---------------------------------------------------------------------------

class NonlinearSystemSolver:
    """
    Monta e resolve o sistema de equações não-lineares do circuito.

    Estratégia dual:
      1. Tentativa rápida com fsolve (Newton-Raphson) — sem bounds.
         Aceito se: convergiu + residual ok + dentro dos bounds + sem explosão.
      2. Fallback robusto com least_squares (TRF) — respeita bounds.
         Usa como warm start o melhor resultado do fsolve (se razoável).

    Parâmetros
    ----------
    components : lista de objetos com interface {variables, equations, bounds}
                 (HydraulicNode + NodeContinuity)
    """

    def __init__(self, components: list):
        self.components = components
        self.var_index: dict[str, int] = {}
        self.index_var: list[str] = []

    def register_variables(self) -> None:
        for comp in self.components:
            for var in comp.variables:
                if var not in self.var_index:
                    self.var_index[var] = len(self.index_var)
                    self.index_var.append(var)

    def build_bounds(self) -> tuple[np.ndarray, np.ndarray]:
        lower = np.full(len(self.index_var), -np.inf)
        upper = np.full(len(self.index_var),  np.inf)

        for comp in self.components:
            if not hasattr(comp, "bounds"):
                continue
            for var, (lo, hi) in comp.bounds.items():
                if var not in self.var_index:
                    continue
                idx = self.var_index[var]
                if lo is not None:
                    lower[idx] = lo
                if hi is not None:
                    upper[idx] = hi

        return lower, upper

    def build_system(self):
        def system(x):
            eqs = []
            for comp in self.components:
                eqs.extend(comp.equations(x, self.var_index))
            return eqs
        return system

    def solve(
        self,
        x0_dict: dict[str, float],
        ctx: ScaleContext,
    ) -> dict[str, float]:
        """
        Resolve o sistema e retorna {variavel: valor}.

        Parâmetros
        ----------
        x0_dict : chute inicial por nome de variável
        ctx     : ScaleContext do circuito atual
        """
        self.register_variables()

        x0 = np.zeros(len(self.index_var))
        for var, val in x0_dict.items():
            if var in self.var_index:
                x0[self.var_index[var]] = val

        lower, upper = self.build_bounds()
        x0 = np.clip(x0, lower, upper)

        system = self.build_system()
        q_ref_safe = max(ctx.q_ref, 1e-12)

        # Escala de normalização mista para o critério de aceitação do fsolve.
        # O sistema tem duas classes de equações com unidades distintas:
        #   - equações de vazão (NodeContinuity, conservação): resíduo em m³/s
        #   - equações de pressão (ΔP–Q das válvulas, etc.): resíduo em Pa
        # Usar apenas q_ref como threshold aceita soluções onde as equações
        # de pressão têm resíduo enorme (ex: 1e5 Pa) sem perceber.
        # A escala mista normaliza ambas as classes para ordem 1.
        _mixed_scale = q_ref_safe + ctx.p_ref / max(ctx.zc, 1.0)

        # ------------------------------------------------------------------ #
        # Tentativa rápida — fsolve (Newton-Raphson)                          #
        # ------------------------------------------------------------------ #
        x_for_ls = x0.copy()

        try:
            x_fast, info, ier, msg = fsolve(system, x0.copy(), full_output=True)
            residual_fast = np.max(np.abs(info["fvec"]))

            within_bounds = (
                np.all(x_fast >= lower - 1e-10) and
                np.all(x_fast <= upper + 1e-10)
            )
            sane = np.all(np.abs(x_fast) < 1e12)

            # Critério normalizado: residual adimensional < 1e-6.
            # Divide pelo _mixed_scale em vez de q_ref_safe puro, para que
            # tanto resíduos de equações de vazão quanto de pressão sejam
            # considerados. Sem isso, um resíduo de 1e5 Pa passa no threshold
            # de q_ref*1e-3 ~ 3e-7 m³/s de um circuito de 20 L/min.
            residual_norm = residual_fast / _mixed_scale
            if ier == 1 and residual_norm < 1e-6 and within_bounds and sane:
                print(f"  fsolve: convergiu | residual_norm={residual_norm:.2e} (raw={residual_fast:.2e})")
                return {var: x_fast[i] for var, i in self.var_index.items()}

            if sane:
                x_for_ls = x_fast  # warm start para least_squares

        except Exception as e:
            print(f"  fsolve: exceção — {e}")

        # ------------------------------------------------------------------ #
        # Fallback robusto — least_squares (TRF)                              #
        # ------------------------------------------------------------------ #
        x_for_ls = np.clip(x_for_ls, lower, upper)

        # Escala explícita por tipo de variável: P-vars em Pa, Q-vars em m³/s.
        # Substituímos x_scale="jac" porque o Jacobiano de circuitos hidráulicos
        # é frequentemente mal-condicionado (razão P/Q ~ 1e8 em 100 bar / 20 L/min),
        # e o escalonamento via Jacobiano herda esse mal-condicionamento em vez
        # de corrigi-lo. Com escala física explícita, TRF opera em variáveis
        # adimensionais de ordem 1, convergindo mais rápido e de forma mais robusta.
        x_scale_arr = np.array([
            ctx.p_ref if var.startswith("P_") else ctx.q_ref
            for var in self.index_var
        ])
        x_scale_arr = np.where(x_scale_arr > 0, x_scale_arr, 1.0)

        result = least_squares(
            system, x_for_ls,
            method="trf",
            bounds=(lower, upper),
            x_scale=x_scale_arr,
            ftol=1e-10,
            xtol=1e-10,
            gtol=1e-10,
            max_nfev=6000,
        )

        residual = np.max(np.abs(result.fun))
        print(
            f"  least_squares: {result.message} | "
            f"residual={residual:.2e} | "
            f"p_ref={ctx.p_ref:.2e} Pa | "
            f"q_ref={ctx.q_ref:.2e} m³/s | "
            f"zc={ctx.zc:.2e}"
        )

        return {var: result.x[i] for var, i in self.var_index.items()}

    def build_initial_guess(
        self,
        hydraulic_nodes: list,
        ctx: ScaleContext,
    ) -> dict[str, float]:
        """
        Monta o chute inicial combinando:
          - initial_guess dos nós (tem precedência)
          - Q_hint global para variáveis de vazão sem guess
        """
        x0: dict[str, float] = {
            var: 0.0
            for node in hydraulic_nodes
            for var in node.variables
        }

        guessed_vars: set[str] = set()
        for node in hydraulic_nodes:
            if hasattr(node, "initial_guess"):
                guess = node.initial_guess
                x0.update(guess)
                guessed_vars.update(guess.keys())

        # escala os sentinelas de sinal (±1.0) para Q_hint
        for var in x0:
            if not var.startswith("Q_"):
                continue
            if var not in guessed_vars and x0[var] == 0.0:
                x0[var] = ctx.q_ref
            elif var in guessed_vars and abs(x0[var]) == 1.0:
                x0[var] = math.copysign(ctx.q_ref, x0[var])

        return x0