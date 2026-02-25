import numpy as np
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
        residual = np.max(np.abs(info['fvec']))
        if ier != 1 and residual > 1e-6:
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
                guess = node.initial_guess()
                x0.update(guess)
                guessed_vars.update(guess.keys())

        hints = [node.flow_hint for node in hydraulic_nodes if hasattr(node, "flow_hint")]
        Q_hint = max(hints) if hints else None
        if Q_hint is not None and Q_hint < 1e-10:
            Q_hint = None  # ignora hints zerados
        print(f"[build_initial_guess] Q_hint={Q_hint}, nodes com flow_hint: {[n.id[:8] for n in hydraulic_nodes if hasattr(n, 'flow_hint')]}")

        if Q_hint:
            for var in x0:
                if var.startswith("Q_") and x0[var] == 0.0 and var not in guessed_vars:
                    x0[var] = Q_hint

        return x0


# ---------------------------------------------------------------------------
# Equação de continuidade gerada automaticamente por grupo de pressão
# ---------------------------------------------------------------------------

class NodeContinuity:
    """
    Gerada automaticamente para cada grupo de anchors hidráulicas conectadas.
    Garante conservação de massa: sum(Q) = 0
    
    Não há sinal explícito — o sinal emerge da solução do sistema.
    Q positivo = fluxo no sentido assumido pelo componente.
    Q negativo = fluxo no sentido oposto.
    """
    def __init__(self, pressure_var, flow_vars):
        self.pressure_var = pressure_var  # nome da variável P_* deste grupo
        self.flow_vars = flow_vars        # list[str] - nomes das variáveis Q_* que tocam este grupo

    @property
    def variables(self):
        return [self.pressure_var]

    def equations(self, x, idx):
        return [sum(x[idx[q]] for q in self.flow_vars if q in idx)]
