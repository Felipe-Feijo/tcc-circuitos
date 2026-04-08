import numpy as np
import math
from scipy.optimize import least_squares


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

    def build_bounds(self):
        lower = np.full(len(self.index_var), -np.inf)
        upper = np.full(len(self.index_var),  np.inf)

        for comp in self.components:
            if not hasattr(comp, 'bounds'):
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

    def build_equations(self):
        def system(x):
            eqs = []
            for comp in self.components:
                eqs.extend(comp.equations(x, self.var_index))
            return eqs
        return system

    def solve(self, x0_dict, q_ref=0, p_ref=0):
        self.register_variables()

        x0 = np.zeros(len(self.index_var))
        for var, val in x0_dict.items():
            if var in self.var_index:
                x0[self.var_index[var]] = val

        lower, upper = self.build_bounds()

        # clipa x0 para dentro dos bounds
        x0 = np.clip(x0, lower, upper)

        system = self.build_equations()

        result = least_squares(
            system, x0,
            method='trf',
            bounds=(lower, upper),
            x_scale='jac',
            ftol=1e-8,
            xtol=1e-8,
            gtol=1e-8,
            max_nfev=6000,
        )

        residual = np.max(np.abs(result.fun))
        q_ref_safe = max(q_ref, 1e-12)
        print(f"least_squares: {result.message} | residual: {residual:.2e} | Q_ref: {q_ref_safe:.2e} | p_ref: {p_ref:.2e}")
        if residual > 10000: #q_ref_safe * 1e-2:
            raise Exception(
                f"least_squares: {result.message} | "
                f"resíduo: {residual:.2e} | Q_ref: {q_ref_safe:.2e}"
            )

        return {var: result.x[idx] for var, idx in self.var_index.items()}

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
    def __init__(self, pressure_var, flow_vars, zc=1e4):
        self.pressure_var = pressure_var
        self.flow_vars = flow_vars
        self.p_previous = 0.0
        self.zc = zc  # instância, não classe

    @property
    def variables(self):
        return [self.pressure_var]
    
    @property
    def bounds(self):
        return {
            self.pressure_var: (0.0, None)  # pressão nunca negativa
        }

    def equations(self, x, idx):
        P = x[idx[self.pressure_var]]
        Q_sum = -sum(x[idx[q]] for q in self.flow_vars if q in idx)
        # normalizado por Q_ref — vem de fora via set_scale
        return [(Q_sum - (P - self.p_previous) / self.zc) / self.q_ref]
    

    def set_scale(self, p_ref, q_ref, zc_gain=10.0):
        if q_ref < 1e-12 or p_ref < 1e-12:
            self.zc = 1
            self.q_ref = 1.0
        else:
            self.zc = (p_ref / q_ref) * zc_gain 
            self.q_ref = q_ref

    def update_pressure(self, sol):
        if self.pressure_var in sol:
            new_p = sol[self.pressure_var]
            # se pressão é ruído numérico, não acumula
            if new_p < self.q_ref * self.zc * 1e-6:
                self.p_previous = 0.0
            else:
                self.p_previous = new_p