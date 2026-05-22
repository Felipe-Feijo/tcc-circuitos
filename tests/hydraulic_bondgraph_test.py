"""Experimento de validação do solver hidráulico usando bond graph e scipy."""

import numpy as np
from scipy.optimize import fsolve

class NonlinearSystemSolver:
    def __init__(self, components):
        self.components = components
        self.var_index = {}
        self.index_var = []

    def register_variables(self):
        """
        Coleta todas as variáveis declaradas pelos componentes
        e monta o mapeamento nome <-> índice.
        """
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
        """
        x0_dict: {nome_variavel: valor_inicial}
        """
        self.register_variables()

        x0 = np.zeros(len(self.index_var))
        for var, val in x0_dict.items():
            x0[self.var_index[var]] = val

        system = self.build_equations()

        sol = fsolve(system, x0)

        return {
            var: sol[idx]
            for var, idx in self.var_index.items()
        }

class Node:
    def __init__(self, id):
        self.id = id

class Valve:
    def __init__(self, id, node_in, node_out, k):
        self.id = id
        self.node_in = node_in
        self.node_out = node_out
        self.k = k

    @property
    def variables(self):
        return [
            f"P_{self.node_in.id}",
            f"P_{self.node_out.id}",
            f"Q_{self.id}",
        ]

    def equations(self, x, idx):
        Pin  = x[idx[f"P_{self.node_in.id}"]]
        Pout = x[idx[f"P_{self.node_out.id}"]]
        Q    = x[idx[f"Q_{self.id}"]]

        return [
            (Pin - Pout) - (Q/self.k)**2
        ]
    
    def ports(self):
        return [
            Port(self.node_in, -1),
            Port(self.node_out, +1)
        ]
class Tank:
    def __init__(self, id, node, pressure):
        self.id = id
        self.node = node
        self.pressure = pressure

    @property
    def variables(self):
        return [
            f"P_{self.node.id}",
            f"Q_{self.id}"
        ]

    def equations(self, x, idx):
        P = x[idx[f"P_{self.node.id}"]]
        return [P - self.pressure]

    def ports(self):
        return [
            Port(self.node, -1)
        ]
    
class PumpWithCurve:
    def __init__(self, id, node_in, node_out, Q_max, H_shutoff):
        """
        Bomba com entrada e saída - pode ser colocada em qualquer lugar do circuito.
        
        node_in: de onde a bomba PUXA fluido
        node_out: para onde a bomba EMPURRA fluido
        Q_max: vazão máxima em pressão zero (ex: 2.5 L/min)
        H_shutoff: head máximo em vazão zero (ex: 20 bar)
        
        Curva: ΔP = H_shutoff * (1 - (Q/Q_max)²)
        onde ΔP = P_out - P_in
        """
        self.id = id
        self.node_in = node_in
        self.node_out = node_out
        self.Q_max = Q_max
        self.H_shutoff = H_shutoff

    @property
    def variables(self):
        return [
            f"P_{self.node_in.id}",
            f"P_{self.node_out.id}",
            f"Q_{self.id}",
        ]

    def equations(self, x, idx):
        Pin  = x[idx[f"P_{self.node_in.id}"]]
        Pout = x[idx[f"P_{self.node_out.id}"]]
        Q    = x[idx[f"Q_{self.id}"]]
        
        # Head (diferencial de pressão) gerado pela bomba
        delta_P = Pout - Pin
        
        # Curva característica
        delta_P_curve = self.H_shutoff * (1 - (Q / self.Q_max)**2)
        
        return [delta_P - delta_P_curve]

    def ports(self):
        return [
            Port(self.node_in, -1),   # puxa do node_in
            Port(self.node_out, +1)   # empurra para node_out
        ]
class NodeContinuity:
    def __init__(self, node, flows_in, flows_out):
        self.node = node
        self.flows_in = flows_in
        self.flows_out = flows_out

    @property
    def variables(self):
        return self.flows_in + self.flows_out

    def equations(self, x, idx):
        Qin = sum(x[idx[q]] for q in self.flows_in)
        Qout = sum(x[idx[q]] for q in self.flows_out)
        return [Qin - Qout]
    
class Port:
    def __init__(self, node, sign):
        self.node = node
        self.sign = sign   # +1 se entra, -1 se sai

class Pistao:
    def __init__(self, id, node, area, mass=1.0, friction=0.1, 
                 external_force=0.0, x0=0.0, x_max=1.0):
        self.id = id
        self.node = node
        self.area = area
        self.mass = mass
        self.friction = friction
        self.external_force = external_force
        self.x = x0
        self.x_max = x_max
        self.velocity = 0.0
        self.locked = False  # novo estado

    @property
    def variables(self):
        return [
            f"P_{self.node.id}",
            f"Q_{self.id}"
        ]

    def equations(self, x, idx):
        P = x[idx[f"P_{self.node.id}"]]
        Q = x[idx[f"Q_{self.id}"]]
        
        # Se pistão travado, vazão = 0
        if self.locked:
            return [Q]  # Q = 0
        
        # Caso contrário, relação força-pressão normal
        v = Q / self.area
        force_hydraulic = P * self.area
        force_resistance = self.friction * v + self.external_force
        
        return [force_hydraulic - force_resistance]

    def ports(self):
        return [Port(self.node, -1)]

    def step(self, Q_in, dt):
        """
        Atualiza a posição do pistão.
        """
        if self.locked:
            return 0.0  # já travado, sem movimento
        
        v = Q_in / self.area
        dx = v * dt
        self.x += dx
        
        if self.x >= self.x_max:
            self.x = self.x_max
            self.locked = True  # TRAVA O PISTÃO
            print(f"  *** PISTÃO TRAVADO EM x={self.x:.4f} ***")
            return 0.0
        
        return 0.0

class ReliefValve:
    def __init__(self, id, node_in, node_out, p_set, k):
        """
        p_set: pressão de abertura
        k: condutância quando totalmente aberta
        """
        self.id = id
        self.node_in = node_in
        self.node_out = node_out
        self.p_set = p_set
        self.k = k

    @property
    def variables(self):
        return [
            f"P_{self.node_in.id}",
            f"P_{self.node_out.id}",
            f"Q_{self.id}",
        ]

    def equations(self, x, idx):
        Pin  = x[idx[f"P_{self.node_in.id}"]]
        Pout = x[idx[f"P_{self.node_out.id}"]]
        Q    = x[idx[f"Q_{self.id}"]]

        delta_p = Pin - Pout
        
        if delta_p <= self.p_set:
            # Fechada: Q = 0 (sem vazamento)
            return [Q]
        else:
            # Aberta: válvula normal
            p_excess = delta_p - self.p_set
            return [p_excess - (Q / self.k)**2]

    def ports(self):
        return [
            Port(self.node_in, -1),
            Port(self.node_out, +1)
        ]

from collections import defaultdict

def build_node_continuities(components):
    node_flows = defaultdict(list)

    for comp in components:
        for port in comp.ports():
            node_flows[port.node.id].append(
                (comp.id, port.sign)
            )

    continuities = []

    for node_id, flows in node_flows.items():
        flows_in = []
        flows_out = []

        for flow_id, sign in flows:
            if sign > 0:
                flows_in.append(f"Q_{flow_id}")
            else:
                flows_out.append(f"Q_{flow_id}")

        continuities.append(
            NodeContinuity(Node(node_id), flows_in, flows_out)
        )

    return continuities



# --- Nós ---
n1 = Node(1)
n2 = Node(2)
n3 = Node(3)
n12 = Node(12)
n_pistao = Node(13)  # nó intermediário entre valve1b e pistão

# --- Componentes ---
pump = PumpWithCurve("pump1", n3, n1, Q_max=2.0, H_shutoff=20.0)

valve1a = Valve("v1a", n1, n12, k=15.0)   # válvula "boa"
valve1b = Valve("v1b", n12, n_pistao, k=30)  # válvula para pistão
#valve2 = Valve("v2", n1, n3, k=0.1)        # outro caminho para tanque

# Pistão conectado ao nó intermediário
pistao = Pistao("pistao1", node=n_pistao, area=1.0, 
                mass=1.0, friction=2.0, external_force=0.0,
                x0=0.0, x_max=1.0)

# Tanque (reservatório) ainda no nó n3
tank = Tank("tank1", n3, pressure=0.0)

relief = ReliefValve("relief1", n1, n3, p_set=10.0, k=3.0)

# --- Lista de componentes ---
components = [
    pump,
    valve1a,
    valve1b,
    #valve2,
    pistao,
    tank,
    relief,
]

# --- Gerar equações de continuidade automaticamente ---
components += build_node_continuities(components)

solver = NonlinearSystemSolver(components)

dt = 0.25  # step time
n_steps = 8

# --- Loop de simulação por steps ---
for step in range(n_steps):
    # Resolver o sistema hidráulico
    sol = solver.solve({
        "Q_pump1": 2.0,
        "P_3": 0.0
    })

    # Atualiza posição do pistão
    Q_in = sol[f"Q_{pistao.id}"]
    Q_excess = pistao.step(abs(Q_in), dt)  # usamos abs para garantir avanço positivo

    # --- Print de pressões e vazões (como antes) ---
    print(f"\nStep {step+1}:")
    print(f"Pistao x = {pistao.x:.4f}, Q_in = {Q_in:.4f}, Q_excess = {Q_excess:.4f}")

    print("Pressões nos nodes:")
    nodes_ids = {n.id for n in [n1, n12, n_pistao, n3]}
    for node_id in nodes_ids:
        key = f"P_{node_id}"
        if key in sol:
            print(f"  Node {node_id}: P = {sol[key]:.4f}")

    print("Vazões nos componentes:")
    for comp in [pump, valve1a, valve1b, relief, pistao]:
        key = f"Q_{comp.id}"
        if key in sol:
            print(f"  {comp.id}: Q = {sol[key]:.4f}")

    # Opcional: redirecionar Q_excess para outro ramo
    # Por exemplo, para valve2/tank
    if Q_excess > 0:
        print(f"  Q_excess do pistão: {Q_excess:.4f} redirecionável")