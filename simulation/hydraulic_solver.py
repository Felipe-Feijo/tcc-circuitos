import numpy as np
import math
from scipy.optimize import fsolve


class NonlinearSystemSolver:
    def __init__(self, components):
        self.components = components
        self.var_index = {}
        self.index_var = []

    def register_variables(self):
        for comp in self.components:
            for var in comp.variables:
                if var not in self.var_index:
                    self.var_index[var] = len(self.index_var)
                    self.index_var.append(var)

    def build_equations(self):
        def system(x):
            eqs = []
            for comp in self.components:
                eqs.extend(comp.equations(x, self.var_index))
            return eqs
        return system

    def solve(self, x0_dict):
        self.register_variables()

        x0 = np.zeros(len(self.index_var))
        for var, val in x0_dict.items():
            if var in self.var_index:
                x0[self.var_index[var]] = val

        system = self.build_equations()
        sol_array, info, ier, msg = fsolve(system, x0, full_output=True)
        self.sol_array = sol_array
        residual = np.max(np.abs(info['fvec']))

        if ier != 1 and residual > 100:
            raise Exception(f"fsolve: {msg} | resíduo: {residual:.2e}")

        return {
            var: sol_array[idx]
            for var, idx in self.var_index.items()
        }

    def build_initial_guess(self, hydraulic_nodes) -> dict:
        x0 = {var: 0.0 for node in hydraulic_nodes for var in node.variables}

        guessed_vars = set()
        for node in hydraulic_nodes:
            if hasattr(node, "initial_guess"):
                guess = node.initial_guess
                x0.update(guess)
                guessed_vars.update(guess.keys())

        Q_hint = next(
            (node.flow_hint for node in hydraulic_nodes
             if hasattr(node, "flow_hint") and node.flow_hint > 1e-10),
            None
        )

        if Q_hint is None:
            Q_hint = self._last_Q_hint if hasattr(self, "_last_Q_hint") else 1e-4
        else:
            self._last_Q_hint = Q_hint

        for var in x0:
            if not var.startswith("Q_"):
                continue
            if var not in guessed_vars and x0[var] == 0.0:
                x0[var] = Q_hint
            elif var in guessed_vars and abs(x0[var]) == 1.0:
                x0[var] = math.copysign(Q_hint, x0[var])

        return x0


class NodeContinuity:
    """
    Equação de continuidade para cada grupo de pressão.
    Com compressibilidade: ΣQ = (P - P_anterior) / Zc
    Zc controla a rigidez do fluido. Zc grande → pressão sobe rápido com pouca vazão residual.
    """
    # Impedância característica — valor alto para pressão subir rápido dentro do loop
    ZC = 1e4

    def __init__(self, pressure_var, flow_vars):
        self.pressure_var = pressure_var
        self.flow_vars = flow_vars
        self.p_previous = 0.0  # atualizado após cada step

    @property
    def variables(self):
        return [self.pressure_var]

    def equations(self, x, idx):
        P = x[idx[self.pressure_var]]
        Q_sum = -sum(x[idx[q]] for q in self.flow_vars if q in idx)
        # ΣQ = (P - P_anterior) / Zc
        return [(Q_sum - (P - self.p_previous) / self.ZC) * 100]

    def update_pressure(self, sol):
        if self.pressure_var in sol:
            self.p_previous = sol[self.pressure_var]