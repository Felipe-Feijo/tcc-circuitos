"""Motor principal de simulação: itera os três domínios até estabilização.

O SimulationEngine não conhece Qt nem itens gráficos. Recebe um grafo de
nós e conexões de domínio e, a cada chamada de run_until_stable(), propaga
estado pelos domínios pneumático, elétrico e hidráulico até que nenhuma
âncora mude de valor — ou até atingir o limite de iterações.
"""

import logging
from collections import defaultdict, deque

from simulation.hydraulic import (
    HydraulicNode,
    NodeContinuity,
    NonlinearSystemSolver,
    ScaleContext,
    ScaleManager,
    ZcScheduler,
    ConvergenceMonitor,
    ConvergenceResult,
)

logger = logging.getLogger(__name__)


class SimulationEngine:
    """Motor de simulação multi-domínio baseado em ponto fixo.

    Itera sobre os três domínios (pneumático, elétrico, hidráulico) em
    sequência até que nenhum âncora mude de estado — indicando estabilização.
    O domínio hidráulico usa um solver não-linear interno com detecção de
    convergência e gerenciamento de escala.

    Args:
        nodes: Dicionário {node_id: Node} construído pelo GraphBuilder.
        connections: Dicionário {connection_id: Connection}.
        max_iterations: Limite de iterações de ponto fixo antes de lançar RuntimeError.
    """
    def __init__(self, nodes, connections, max_iterations=100):
        self.nodes = nodes
        self.connections = connections
        self.max_iterations = max_iterations
        self.outputs = {}
        self._continuities: dict[str, NodeContinuity] = {}
        self._prev_circuit_map = {}
        self._hydraulic_iteration = 0

        self._hydraulic_max_iterations = 15

        self._scale_manager = ScaleManager()
        self._zc_scheduler  = ZcScheduler()
        self._conv_monitor  = ConvergenceMonitor()

    def run_until_stable(self, dt=0.1):
        """Executa iterações de ponto fixo até estabilização dos três domínios.

        A cada iteração, chama node.update() em todos os nós e propaga estado
        pelos domínios pneumático, elétrico e hidráulico. Para quando nenhum
        domínio reporta mudança. Após estabilizar, chama compute_outputs().

        Args:
            dt: Intervalo de tempo em segundos para post_step_update.

        Raises:
            RuntimeError: Se o número de iterações exceder max_iterations.
        """
        iteration = 0

        if not self.outputs:
            # Semeia engine.outputs com os outputs iniciais dos nós (ex: sensores
            # de cilindro baseados no default_state) para que o primeiro update
            # já receba valores corretos em vez de outputs={}.
            for node in self.nodes.values():
                node_outputs = getattr(node, "outputs", None)
                if node_outputs:
                    for name, payload in node_outputs.items():
                        self.outputs[name] = payload

        while True:
            iteration += 1
            if iteration > self.max_iterations:
                raise RuntimeError(
                    f"Simulation did not stabilize after {self.max_iterations} iterations."
                )

            for node in self.nodes.values():
                node.update(self.outputs)

            changed = False
            changed |= self._update_pneumatic_domain()
            changed |= self._update_electric_domain()
            changed |= self._update_hydraulic_domain()

            if not changed:
                break

        self.compute_outputs(dt=dt)

    def compute_outputs(self, dt):
        """Coleta os outputs de todos os nós após a estabilização.

        Chama post_step_update(dt) em cada nó e agrega os valores de
        node.outputs no dicionário self.outputs, usado como entrada da
        próxima iteração de run_until_stable.

        Args:
            dt: Intervalo de tempo em segundos desde o último passo.
        """
        self.outputs = {}

        for node in self.nodes.values():
            node.post_step_update(dt=dt)

            node_outputs = getattr(node, "outputs", None)
            if not node_outputs:
                continue

            for name, payload in node_outputs.items():
                self.outputs[name] = payload

    def _update_pneumatic_domain(self):
        visited = set()
        changed = False

        for node in self.nodes.values():
            for anchor in node.anchors.values():
                if anchor.domain != "pneumatic":
                    continue
                if anchor in visited:
                    continue

                group = self._get_connected_group(anchor)
                visited.update(group)

                drivers = [a for a in group if a.is_driver]
                if not drivers:
                    continue

                group_state = all(d.state for d in drivers)

                for a in group:
                    if not a.is_driver and a.state != group_state:
                        a.state = group_state
                        changed = True

        return changed

    def _get_connected_group(self, start_anchor, internal=True):
        group = set()
        queue = deque([start_anchor])
        domain = start_anchor.domain

        while queue:
            anchor = queue.popleft()
            if anchor in group:
                continue
            group.add(anchor)

            if internal:
                for a_id, b_id in anchor.node.get_internal_connections():
                    a_anchor = anchor.node.get_anchor(a_id)
                    b_anchor = anchor.node.get_anchor(b_id)
                    other = (
                        b_anchor if a_anchor == anchor
                        else a_anchor if b_anchor == anchor
                        else None
                    )
                    if other and other.domain == domain and other not in group:
                        queue.append(other)

            for conn in anchor.connections:
                other = conn.get_other(anchor)
                if other.domain == domain and other not in group:
                    queue.append(other)

        return group

    def _update_electric_domain(self):
        changed = False

        valid_anchors = self._compute_valid_electric_anchors()

        for node in self.nodes.values():
            for a in node.anchors.values():
                if a.domain != "electric":
                    continue
                new_state = a in valid_anchors
                if a.state != new_state:
                    a.state = new_state
                    changed = True

        return changed

    def _compute_valid_electric_anchors(self):
        """Determina quais anchors elétricas estão em algum caminho fonte->terra.

        Um anchor está "energizado" se existe algum caminho simples de uma
        anchor tipo "source" até uma anchor tipo "ground" passando por ele —
        não basta estar no mesmo componente conexo (um ramo sem saída
        pendurado no meio do caminho não conduz).

        Calculado em O(V+E) via pontes (Tarjan): colapsa cada componente
        2-aresta-conexo (ex: dois contatos em paralelo que se reconvergem)
        num único nó, e resolve "está entre fonte e terra?" com uma única
        passada de DP na árvore de pontes resultante — sem reexplorar a
        mesma sub-região do grafo mais de uma vez.
        """
        anchors = [
            a for node in self.nodes.values() for a in node.anchors.values()
            if a.domain == "electric"
        ]
        if not anchors:
            return set()

        adjacency = self._build_electric_adjacency(anchors)
        bridges = self._find_bridges(anchors, adjacency)
        comp_of = self._electric_components(anchors, adjacency, bridges)
        valid_components = self._valid_bridge_tree_components(anchors, adjacency, bridges, comp_of)

        return {a for a in anchors if comp_of[a] in valid_components}

    def _build_electric_adjacency(self, anchors):
        adjacency = defaultdict(list)
        next_edge_id = [0]

        def add_edge(a, b):
            edge_id = next_edge_id[0]
            next_edge_id[0] += 1
            adjacency[a].append((b, edge_id))
            adjacency[b].append((a, edge_id))

        for node in self.nodes.values():
            for a_id, b_id in node.get_internal_connections():
                a_anchor = node.get_anchor(a_id)
                b_anchor = node.get_anchor(b_id)
                if a_anchor.domain == "electric" and b_anchor.domain == "electric":
                    add_edge(a_anchor, b_anchor)

        seen_conns = set()
        for a in anchors:
            for conn in a.connections:
                if id(conn) in seen_conns:
                    continue
                seen_conns.add(id(conn))
                other = conn.get_other(a)
                if other.domain == "electric":
                    add_edge(a, other)

        return adjacency

    def _find_bridges(self, anchors, adjacency):
        """Tarjan: arestas cuja remoção desconecta o grafo (low-link)."""
        disc = {}
        low = {}
        bridges = set()
        timer = [0]

        def dfs(u, parent_edge):
            disc[u] = low[u] = timer[0]
            timer[0] += 1
            for v, edge_id in adjacency[u]:
                if edge_id == parent_edge:
                    continue
                if v not in disc:
                    dfs(v, edge_id)
                    low[u] = min(low[u], low[v])
                    if low[v] > disc[u]:
                        bridges.add(edge_id)
                else:
                    low[u] = min(low[u], disc[v])

        for a in anchors:
            if a not in disc:
                dfs(a, None)

        return bridges

    def _electric_components(self, anchors, adjacency, bridges):
        """Une anchors ligados por arestas que NÃO são pontes (union-find)."""
        parent = {a: a for a in anchors}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        seen_edges = set()
        for u in anchors:
            for v, edge_id in adjacency[u]:
                if edge_id in seen_edges:
                    continue
                seen_edges.add(edge_id)
                if edge_id not in bridges:
                    root_u, root_v = find(u), find(v)
                    if root_u != root_v:
                        parent[root_u] = root_v

        return {a: find(a) for a in anchors}

    def _valid_bridge_tree_components(self, anchors, adjacency, bridges, comp_of):
        """Marca componentes que ficam entre uma fonte e uma terra na árvore de pontes."""
        local_source = defaultdict(int)
        local_ground = defaultdict(int)
        for a in anchors:
            comp = comp_of[a]
            if a.type == "source":
                local_source[comp] += 1
            elif a.type == "ground":
                local_ground[comp] += 1

        comp_adj = defaultdict(list)
        seen_edges = set()
        for u in anchors:
            for v, edge_id in adjacency[u]:
                if edge_id not in bridges or edge_id in seen_edges:
                    continue
                seen_edges.add(edge_id)
                comp_u, comp_v = comp_of[u], comp_of[v]
                if comp_u != comp_v:
                    comp_adj[comp_u].append((comp_v, edge_id))
                    comp_adj[comp_v].append((comp_u, edge_id))

        valid_components = set()
        visited_components = set()
        for root in set(comp_of.values()):
            if root in visited_components:
                continue
            self._process_bridge_tree(
                root, comp_adj, local_source, local_ground, visited_components, valid_components
            )

        return valid_components

    def _process_bridge_tree(self, root, comp_adj, local_source, local_ground, visited_components, valid_components):
        """DP numa árvore de pontes: soma fontes/terras por subárvore e decide,
        por componente, se existem dois "braços" distintos (local ou vizinho)
        que juntos cobrem uma fonte e uma terra."""
        parent = {root: None}
        parent_edge = {root: None}
        order = [root]
        queue = deque([root])
        visited_components.add(root)
        while queue:
            u = queue.popleft()
            for v, edge_id in comp_adj[u]:
                if v not in parent:
                    parent[v] = u
                    parent_edge[v] = edge_id
                    order.append(v)
                    visited_components.add(v)
                    queue.append(v)

        count_s = {c: local_source.get(c, 0) for c in order}
        count_g = {c: local_ground.get(c, 0) for c in order}
        for c in reversed(order):
            p = parent[c]
            if p is not None:
                count_s[p] += count_s[c]
                count_g[p] += count_g[c]

        total_s = count_s[root]
        total_g = count_g[root]

        for c in order:
            if local_source.get(c, 0) > 0 and local_ground.get(c, 0) > 0:
                # Fonte e terra caem no mesmo bloco 2-aresta-conexo (ex: dois
                # contatos independentes do mesmo relé fechados ao mesmo tempo,
                # cada um completando um caminho fonte->terra por rota
                # diferente) -- a corrente fecha dentro do próprio bloco, sem
                # precisar de "braços" externos distintos.
                valid_components.add(c)
                continue

            s_arms = set()
            g_arms = set()
            if local_source.get(c, 0) > 0:
                s_arms.add("local")
            if local_ground.get(c, 0) > 0:
                g_arms.add("local")

            for v, edge_id in comp_adj[c]:
                if parent.get(v) == c:
                    region_s, region_g = count_s[v], count_g[v]
                else:
                    region_s = total_s - count_s[c]
                    region_g = total_g - count_g[c]
                if region_s > 0:
                    s_arms.add(edge_id)
                if region_g > 0:
                    g_arms.add(edge_id)

            if not s_arms or not g_arms:
                continue
            if s_arms != g_arms or len(s_arms) > 1:
                valid_components.add(c)

    P_MAX = 10e8

    def _check_flow_conservation(
        self,
        circuit_nodes: list,
        anchor_to_pressure_var: dict,
    ) -> bool:
        """Delega verificação ao ConvergenceMonitor."""
        _, q_ref = self._scale_manager.estimate(circuit_nodes)
        result = self._conv_monitor.check(
            self._continuities, anchor_to_pressure_var, q_ref
        )
        self._conv_monitor.apply_pressurizing_flags(result, anchor_to_pressure_var)
        return result.converged

    def _reset_continuity(self, pvar: str):
        cont = self._continuities.get(pvar)
        if cont:
            cont.reset()

    def _reset_circuit_continuities(self, circuit_pvars):
        for pvar in circuit_pvars:
            if pvar in self._continuities:
                self._reset_continuity(pvar)

    def _update_hydraulic_domain(self) -> bool:
        hydraulic_nodes = self._collect_hydraulic_nodes()
        if not hydraulic_nodes:
            return False

        anchor_to_pressure_var = self._assign_pressure_vars()
        circuits = self._partition_circuits(hydraulic_nodes, anchor_to_pressure_var)

        for i, (circuit_pvars, circuit_nodes) in enumerate(circuits):
            ctx = self._scale_manager.build_context(
                list(circuit_nodes),
                self._hydraulic_iteration,
                self._zc_scheduler,
            )
            self._solve_circuit(
                i + 1, circuit_nodes, circuit_pvars, anchor_to_pressure_var,
                ctx=ctx,
                debug=False,
            )

        converged = self._check_flow_conservation(hydraulic_nodes, anchor_to_pressure_var)

        if converged:
            self._hydraulic_iteration = 0
            return False

        self._hydraulic_iteration += 1

        if self._hydraulic_iteration >= self._hydraulic_max_iterations:
            self._hydraulic_iteration = 0
            logger.warning(
                "domínio hidráulico não convergiu após %d iterações.",
                self._hydraulic_max_iterations,
            )
            return False

        return True

    def _collect_hydraulic_nodes(self) -> list:
        return [n for n in self.nodes.values() if isinstance(n, HydraulicNode) and getattr(n, "domain", None) == "hydraulic"]

    def _assign_pressure_vars(self) -> dict:
        visited_anchors = set()
        anchor_to_pressure_var = {}

        for node in self.nodes.values():
            for anchor in node.anchors.values():
                if anchor.domain != "hydraulic" or anchor in visited_anchors:
                    continue

                group = self._get_connected_group(anchor, internal=False)
                visited_anchors.update(group)

                representative = min(group, key=lambda a: str(a.id))
                pressure_var = f"P_{representative.node.id}_{representative.name}"

                for a in group:
                    anchor_to_pressure_var[a] = pressure_var
                    a.pressure_var = pressure_var

        return anchor_to_pressure_var

    def _partition_circuits(self, hydraulic_nodes, anchor_to_pressure_var):
        pressure_var_to_nodes = defaultdict(set)
        node_to_pressure_vars = defaultdict(set)

        for node in hydraulic_nodes:
            for anchor_name in node.hydraulic_ports():
                anchor = node.anchors.get(anchor_name)
                if anchor:
                    pvar = anchor_to_pressure_var.get(anchor)
                    if pvar:
                        pressure_var_to_nodes[pvar].add(node)
                        node_to_pressure_vars[node].add(pvar)

            # Inclui todas as portas fisicas do no no grafo de conectividade
            # (nao so as ativas). Uma valvula direcional tem portas bloqueadas
            # que ainda estao ligadas por fios — sem isso, a bomba fica num
            # circuito separado do cilindro quando a valvula comuta.
            # Nota: isso so afeta a PARTICAO (quem esta no mesmo circuito),
            # nao as equacoes — as portas bloqueadas nao entram no solve.
            for anchor_name, anchor in node.anchors.items():
                if anchor.domain != "hydraulic":
                    continue
                pvar = anchor_to_pressure_var.get(anchor)
                if pvar:
                    pressure_var_to_nodes[pvar].add(node)
                    node_to_pressure_vars[node].add(pvar)

            for anchor_name_a, anchor_name_b in (node.get_internal_connections() or []):
                anchor_a = node.anchors.get(anchor_name_a)
                anchor_b = node.anchors.get(anchor_name_b)
                if anchor_a and anchor_b:
                    pvar_a = anchor_to_pressure_var.get(anchor_a)
                    pvar_b = anchor_to_pressure_var.get(anchor_b)
                    if pvar_a and pvar_b and pvar_a != pvar_b:
                        pressure_var_to_nodes[pvar_a].add(node)
                        pressure_var_to_nodes[pvar_b].add(node)
                        node_to_pressure_vars[node].add(pvar_a)
                        node_to_pressure_vars[node].add(pvar_b)

        def expand_circuit(start_pvar):
            visited = set()
            queue = [start_pvar]
            while queue:
                pvar = queue.pop()
                if pvar in visited:
                    continue
                visited.add(pvar)
                for node in pressure_var_to_nodes[pvar]:
                    for other_pvar in node_to_pressure_vars[node]:
                        if other_pvar not in visited:
                            queue.append(other_pvar)
            return visited

        remaining_pvars = set(pressure_var_to_nodes.keys())
        circuits = []

        while remaining_pvars:
            start = next(iter(remaining_pvars))
            circuit_pvars = expand_circuit(start)
            circuit_nodes = {
                node for pvar in circuit_pvars
                for node in pressure_var_to_nodes[pvar]
            }
            circuits.append((circuit_pvars, circuit_nodes))
            remaining_pvars -= circuit_pvars

        return circuits

    def _solve_circuit(self, index, circuit_nodes, circuit_pvars, anchor_to_pressure_var, ctx: ScaleContext, debug=False):
        circuit_list = list(circuit_nodes)
        new_nodes_set = set(circuit_list)

        # circuito morto — nem chama o solver.
        # Criterio: nenhum no tem is_flow_source=True, ou seja, nao ha
        # fonte de fluxo ativa (bomba ligada, cilindro com mola comprimida).
        # Desacoplado do flow_hint para que o ScaleManager possa usar
        # flow_hint como pura ordem de grandeza sem carregar semantica de estado.
        has_flow_source = any(
            getattr(n, "is_flow_source", False)
            for n in circuit_list
        )
        if not has_flow_source:
            sol = {}
            for node in circuit_list:
                for anchor_name, flow_var in node.hydraulic_ports().items():
                    anchor = node.anchors.get(anchor_name)
                    if not anchor:
                        continue
                    pvar = anchor_to_pressure_var.get(anchor)
                    if pvar:
                        cont = self._continuities.get(pvar)
                        sol[pvar] = cont.p_previous if cont else 0.0
                    sol[flow_var] = 0.0
            if debug:
                _print_circuit_state(index, circuit_list, anchor_to_pressure_var, sol)
            self._write_circuit_results(circuit_list, circuit_pvars, anchor_to_pressure_var, sol)
            return

        # circuito ativo — verifica mudança de topologia
        for pvar in circuit_pvars:
            prev_nodes = self._prev_circuit_map.get(pvar)
            if prev_nodes is not None and prev_nodes != new_nodes_set:
                # Mudanca de topologia detectada (valvula comutou, cilindro travou, etc).
                # Em vez de zerar p_previous (que jogaria o solver para o ponto trivial
                # e causaria dezenas de iteracoes de least_squares ate o zc escalar),
                # re-seed com p_ref — o mesmo chute usado na criacao do NodeContinuity.
                cont = self._continuities.get(pvar)
                if cont:
                    cont.p_previous = ctx.p_ref
            self._prev_circuit_map[pvar] = new_nodes_set

        sol = self._try_solve(index, circuit_list, anchor_to_pressure_var, ctx=ctx)

        if debug and sol:
            _print_circuit_state(index, circuit_list, anchor_to_pressure_var, sol)

        if sol is None:
            self._reset_circuit_continuities(circuit_pvars)
            self._mark_circuit_fault(circuit_list, circuit_pvars, anchor_to_pressure_var)
            return

        for pvar, continuity in self._continuities.items():
            if pvar in circuit_pvars:
                continuity.update_pressure(sol)

        # Só atualiza a memória de escala se a solução é fisicamente válida.
        # Uma solução espúria (balanço de vazão ruim) não deve "ensinar" o
        # ScaleManager — caso contrário, um q_ref absurdo pode contaminar
        # os solves seguintes via EMA.
        _, q_ref_check = self._scale_manager.estimate(circuit_list)
        sol_q_values = [abs(v) for k, v in sol.items()
                        if k.startswith("Q_") and isinstance(v, float)]
        max_q = max(sol_q_values) if sol_q_values else 0.0
        q_is_sane = max_q < q_ref_check * 1e3   # no máximo 1000x o q_ref esperado
        p_values_sol = [v for k, v in sol.items()
                        if k.startswith("P_") and isinstance(v, float) and v >= 0]
        max_p = max(p_values_sol) if p_values_sol else 0.0
        p_is_sane = max_p < self.P_MAX

        if q_is_sane and p_is_sane:
            self._scale_manager.update_from_solution(sol)
        else:
            logger.debug(
                "solução rejeitada pelo ScaleManager: max_q=%.2e, max_p=%.2e",
                max_q, max_p,
            )

        self._write_circuit_results(circuit_list, circuit_pvars, anchor_to_pressure_var, sol)

    def _try_solve(self, index, circuit_list, anchor_to_pressure_var, ctx: ScaleContext):
        group_flows = defaultdict(list)
        for node in circuit_list:
            for anchor_name, flow_var in node.hydraulic_ports().items():
                anchor = node.anchors.get(anchor_name)
                if not anchor:
                    continue
                pvar = anchor_to_pressure_var.get(anchor)
                if pvar:
                    group_flows[pvar].append(flow_var)

        # p_ref do circuito — usado para seed de novos NodeContinuity
        circuit_p_ref = ctx.p_ref

        continuities = []
        for pvar, flow_vars in group_flows.items():
            if pvar not in self._continuities:
                cont = NodeContinuity(pvar, flow_vars)
                # Seed inicial: usa p_ref do circuito como chute de pressão.
                # Sem isso, p_previous=0 faz o solver convergir para o ponto
                # trivial (tudo a zero) em vez do estado estacionário real.
                # O solver vai refinar a partir daqui — não é um valor fixado.
                cont.p_previous = circuit_p_ref
                self._continuities[pvar] = cont
            else:
                self._continuities[pvar].flow_vars = flow_vars

            self._continuities[pvar].apply_context(ctx)
            continuities.append(self._continuities[pvar])

        for node in circuit_list:
            if hasattr(node, "set_scale"):
                node.set_scale(ctx.p_ref, ctx.q_ref)

        solver = NonlinearSystemSolver(circuit_list + continuities)
        x0 = solver.build_initial_guess(circuit_list, ctx)

        for cont in continuities:
            pvar = cont.pressure_var
            if pvar in solver.var_index:
                x0[pvar] = cont.p_previous if cont.p_previous > 1.0 else ctx.zc * ctx.q_ref

        try:
            return solver.solve(x0, ctx)
        except Exception as e:
            logger.warning("circuito %d: solver falhou — %s", index, e)
            return None

    def _write_circuit_results(self, circuit_nodes, circuit_pvars, anchor_to_pressure_var, sol):
        for anchor, pvar in anchor_to_pressure_var.items():
            if pvar not in circuit_pvars:
                continue
            if pvar in sol:
                anchor.pressure = sol[pvar]
                anchor.fault = False
                anchor.pressurizing = False

        for node in circuit_nodes:
            node.fault = False
            for anchor in node.anchors.values():
                if anchor.domain != "hydraulic":
                    continue
                anchor.flow = 0.0

            for anchor_name, flow_var in node.hydraulic_ports().items():
                anchor = node.anchors.get(anchor_name)
                if anchor and flow_var in sol:
                    anchor.flow = sol[flow_var]

    def _mark_circuit_fault(self, circuit_list, circuit_pvars, anchor_to_pressure_var):
        for node in circuit_list:
            node_hydraulic_anchors = {
                a for a in node.anchors.values()
                if a.domain == "hydraulic"
            }

            if not node_hydraulic_anchors:
                continue

            any_fault = False
            all_fault = True

            for anchor in node_hydraulic_anchors:
                pvar = anchor_to_pressure_var.get(anchor)
                if pvar and pvar in circuit_pvars:
                    anchor.fault = True
                    anchor.pressurizing = False
                    anchor.pressure = "ERR"
                    anchor.flow = "ERR"
                    any_fault = True
                else:
                    all_fault = False

            if any_fault and all_fault:
                node.fault = True


def _print_circuit_state(index, circuit_list, anchor_to_pressure_var, sol):
    SEP = "─" * 60
    print(f"\n{SEP}")
    print(f"  CIRCUITO {index}")
    print(SEP)

    # pressões por nó de pressão
    pvars_seen = set()
    print("\n  PRESSÕES:")
    for anchor, pvar in anchor_to_pressure_var.items():
        if pvar in sol and pvar not in pvars_seen:
            pvars_seen.add(pvar)
            print(f"    {pvar:45s} = {sol[pvar]:+.4e} Pa")

    # vazões por componente
    print("\n  VAZÕES:")
    for node in circuit_list:
        ports = node.hydraulic_ports() if hasattr(node, 'hydraulic_ports') else {}
        if not ports:
            continue
        print(f"\n    [{node.__class__.__name__}] id={node.id}")
        for anchor_name, flow_var in ports.items():
            anchor = node.anchors.get(anchor_name)
            pvar   = anchor_to_pressure_var.get(anchor, "?")
            P_val  = sol.get(pvar, float('nan'))
            Q_val  = sol.get(flow_var, float('nan'))
            arrow  = "→" if Q_val >= 0 else "←"
            print(f"      porta {anchor_name}: P={P_val:+.4e} Pa  Q={Q_val:+.4e} m³/s  {arrow}")

    print(f"\n{SEP}\n")