from collections import defaultdict

from simulation.hydraulic_solver import NodeContinuity, NonlinearSystemSolver

class SimulationEngine:
    def __init__(self, nodes, connections, max_iterations=100):
        self.nodes = nodes          # dict[id, Node]
        self.connections = connections
        self.max_iterations = max_iterations   

        self.outputs = {}        # dict[name, payload] 

    def run_until_stable(self, dt = 0.1):
        """
        Resolve until no domain propagation changes.
        Internal Node changes (FSM, timers, position) don't prevent stabilization.
        """
        iteration = 0

        while True:
            iteration += 1
            if iteration > self.max_iterations:
                raise RuntimeError(
                    f"Simulation did not stabilize after {self.max_iterations} iterations. "
                    "Possible feedback loop or invalid topology."
                )

            # 1) Update internal node logic (domain agnostic)
            for node in self.nodes.values():
                node.update(self.outputs)

            # 2) Domain-specific propagation
            changed = False
            changed |= self._update_pneumatic_domain()
            changed |= self._update_hydraulic_domain()
            changed |= self._update_electric_domain()

            # 3) Stop when nothing changed
            if not changed:
                break

        # 4) Pós-step (fora do loop de estabilização!)
        self.compute_outputs(dt=dt)
        
    def compute_outputs(self, dt):
        self.outputs = {}

        for node in self.nodes.values():
            node.post_step_update(dt=dt)

            node_outputs = getattr(node, "outputs", None)
            if not node_outputs:
                continue

            for name, payload in node_outputs.items():
                self.outputs[name] = payload


    def _update_pneumatic_domain(self):
        """
        Propagate pneumatic pressure through connected anchor groups.
        Returns True if any anchor state changed.
        """
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
        """BFS to collect all directly or indirectly connected anchors in the same domain."""
        group = set()
        queue = [start_anchor]
        domain = start_anchor.domain

        while queue:
            anchor = queue.pop(0)
            if anchor in group:
                continue

            group.add(anchor)

            # Internal node connections (state-dependent)
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

            # External connections
            for conn in anchor.connections:
                other = conn.get_other(anchor)
                if other.domain == domain and other not in group:
                    queue.append(other)

        return group
    
    def _update_electric_domain(self):
            """
            Propaga state binário pelo domínio elétrico.
            """
            changed = False
            
            # Para cada source, marca caminhos válidos
            valid_anchors = set()
            for node in self.nodes.values():
                for source in node.anchors.values():
                    if source.type == "source":
                        visited = set()
                        self._mark_valid_from_source(source, visited, valid_anchors)
            
            # Atualiza estados
            for node in self.nodes.values():
                for a in node.anchors.values():
                    if a.domain != "electric":
                        continue
                    new_state = a in valid_anchors
                    if a.state != new_state:
                        a.state = new_state
                        changed = True

            return changed

    def _mark_valid_from_source(self, anchor, visited, valid_anchors):
        """
        Marca anchor como válida se ela pode alcançar ground.
        Explora TODOS os caminhos possíveis através de backtracking.
        """
        if anchor in visited:
            return False
        
        visited.add(anchor)
        
        # Ground sempre é válido
        if anchor.type == "ground":
            valid_anchors.add(anchor)
            visited.remove(anchor)
            return True
        
        reaches_ground = False
        
        # Conexões internas - explora TODAS
        for a_id, b_id in anchor.node.get_internal_connections():
            a_anchor = anchor.node.get_anchor(a_id)
            b_anchor = anchor.node.get_anchor(b_id)
            
            other = None
            if a_anchor == anchor:
                other = b_anchor
            elif b_anchor == anchor:
                other = a_anchor
            
            if other and other.domain == "electric":
                if self._mark_valid_from_source(other, visited, valid_anchors):
                    reaches_ground = True
                    # ❌ NÃO faz break aqui! Continua explorando outros caminhos
        
        # Conexões externas - explora TODAS
        for conn in anchor.connections:
            other = conn.get_other(anchor)
            if other and other.domain == "electric":
                if self._mark_valid_from_source(other, visited, valid_anchors):
                    reaches_ground = True
                    # ❌ NÃO faz break aqui! Continua explorando outros caminhos
        
        visited.remove(anchor)
        
        # Marca como válida se alcança ground por QUALQUER caminho
        if reaches_ground:
            valid_anchors.add(anchor)
        
        return reaches_ground
    
    def _update_hydraulic_domain(self):
        hydraulic_nodes = self._collect_hydraulic_nodes()
        if not hydraulic_nodes:
            return False

        anchor_to_pressure_var = self._assign_pressure_vars()
        circuits = self._partition_circuits(hydraulic_nodes, anchor_to_pressure_var)

        changed = False
        for i, (circuit_pvars, circuit_nodes) in enumerate(circuits):
            result = self._solve_circuit(i + 1, circuit_nodes, circuit_pvars, anchor_to_pressure_var)
            changed |= result

        return changed


    def _collect_hydraulic_nodes(self):
        return [
            node for node in self.nodes.values()
            if hasattr(node, 'variables') and hasattr(node, 'equations') and hasattr(node, 'hydraulic_ports')
        ]


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
            circuit_nodes = {node for pvar in circuit_pvars for node in pressure_var_to_nodes[pvar]}
            circuits.append((circuit_pvars, circuit_nodes))
            remaining_pvars -= circuit_pvars

        return circuits


    def _solve_circuit(self, index, circuit_nodes, circuit_pvars, anchor_to_pressure_var):
        circuit_list = list(circuit_nodes)
        changed = False

        sol = self._try_solve(index, circuit_list, anchor_to_pressure_var)

        if sol is None:
            relief_valves = [
                n for n in circuit_list
                if hasattr(n, "open_relief") and not n._open
            ]
            relief_valves_sorted = sorted(relief_valves, key=lambda v: v.p_set)
            
            for rv in relief_valves_sorted:
                rv.open_relief()
                print(f"  abrindo relief {rv.id[:8]} p_set={rv.p_set}")
                sol = self._try_solve(index, circuit_list, anchor_to_pressure_var)
                print(f"  tentativa: {'convergiu' if sol else 'falhou'}")
                if sol is not None:
                    break  # convergiu com o mínimo de reliefs abertas
                print(f"  segunda tentativa: {'convergiu' if sol else 'falhou'}")

        if sol is None:
            locked_cylinders = [
                n for n in circuit_list
                if getattr(n, "locked", False) or
                getattr(n, "locked_fwd", False) or
                getattr(n, "locked_bwd", False)
            ]
            print(f"circuito {index}: {len(locked_cylinders)} cilindro(s) travado(s)")
            if locked_cylinders:
                reduced_list = [n for n in circuit_list if n not in locked_cylinders]
                for node in locked_cylinders:
                    for anchor in node.anchors.values():
                        if anchor.domain == "hydraulic":
                            anchor.flow = 0.0
                sol = self._try_solve(index, reduced_list, anchor_to_pressure_var)
                print(f"  terceira tentativa: {'convergiu' if sol else 'falhou'}")

        if sol is None:
            blocked_cylinders = [
                n for n in circuit_list
                if hasattr(n, "x") and n.x <= 0.0 and
                (getattr(n, "spring_k", 0.0) * n.x + getattr(n, "external_force", 0.0)) > 0
            ]
            if blocked_cylinders:
                reduced_list = [n for n in circuit_list if n not in blocked_cylinders]
                for node in blocked_cylinders:
                    for anchor in node.anchors.values():
                        if anchor.domain == "hydraulic":
                            anchor.flow = 0.0
                sol = self._try_solve(index, reduced_list, anchor_to_pressure_var)
                print(f"  quarta tentativa sem cilindros bloqueados: {'convergiu' if sol else 'falhou'}")

        if sol is None:
            self._mark_circuit_fault(circuit_pvars, anchor_to_pressure_var)
            return False

        # verifica pressões excedendo p_set — abre apenas menor p_set por grupo
        pressure_relief_valves = [
            n for n in circuit_list
            if hasattr(n, "open_relief") and not n._open
            and n.anchors.get("P")
            and n.anchors["P"].pressure_var
            and n.anchors["P"].pressure_var in sol
            and sol[n.anchors["P"].pressure_var] >= n.p_set
        ]
        if pressure_relief_valves:
            relief_by_group = defaultdict(list)
            for rv in pressure_relief_valves:
                anchor = rv.anchors.get("P")
                key = anchor.pressure_var if anchor and anchor.pressure_var else None
                relief_by_group[key].append(rv)

            for group, valves in relief_by_group.items():
                best = min(valves, key=lambda v: v.p_set)
                best.open_relief()
                print(f"  abrindo relief por pressão {best.id[:8]} P={sol[best.anchors['P'].pressure_var]:.2e} p_set={best.p_set}")

            sol = self._try_solve(index, circuit_list, anchor_to_pressure_var)
            print(f"  tentativa com relief por pressão: {'convergiu' if sol else 'falhou'}")
            if sol is None:
                self._mark_circuit_fault(circuit_pvars, anchor_to_pressure_var)
                return False

        old_pressures = {
            anchor: anchor.pressure
            for anchor, pvar in anchor_to_pressure_var.items()
            if pvar in sol
        }

        self._write_circuit_results(circuit_list, anchor_to_pressure_var, sol)

        for anchor, pvar in anchor_to_pressure_var.items():
            if pvar in sol:
                old_p = old_pressures.get(anchor)
                new_p = sol[pvar]
                old_val = old_p if not isinstance(old_p, str) else None
                if old_val is None or abs(new_p - old_val) > 1e-10:
                    changed = True
                    break

        return changed

    def _try_solve(self, index, circuit_list, anchor_to_pressure_var):
        group_flows = defaultdict(list)
        for node in circuit_list:
            for anchor_name, flow_var in node.hydraulic_ports().items():
                anchor = node.anchors.get(anchor_name)
                if not anchor:
                    continue
                pvar = anchor_to_pressure_var.get(anchor)
                if pvar:
                    group_flows[pvar].append(flow_var)

        continuities = [
            NodeContinuity(pvar, flow_vars)
            for pvar, flow_vars in group_flows.items()
        ]

        solver = NonlinearSystemSolver(circuit_list + continuities)
        x0 = solver.build_initial_guess(circuit_list)

        try:
            return solver.solve(x0)
        except Exception as e:
            print(f"circuito {index}: falhou — {e}")
            print(f"[resíduos]:")
            for comp in solver.components:
                eqs = comp.equations(solver.sol_array, solver.var_index)
                name = getattr(comp, 'id', getattr(comp, 'pressure_var', str(comp)))
                print(f"  {str(name)[-8:]}: {[f'{r:.4e}' for r in eqs]}")
            print(f"[x0]:")
            for var, val in x0.items():
                print(f"  {var[-16:]} = {val:.4e}")
            return None


    def _write_circuit_results(self, circuit_nodes, anchor_to_pressure_var, sol):
        # pressão — escreve em TODAS as anchors do grupo, ativas ou não
        for anchor, pvar in anchor_to_pressure_var.items():
            if pvar in sol:
                anchor.pressure = sol[pvar]
                anchor.fault = False

        # flow — só nas anchors ativas nos ports
        for node in circuit_nodes:
            node.fault = False
            for anchor in node.anchors.values():
                if anchor.domain != "hydraulic":
                    continue
                anchor.flow = 0.0  # reseta — sobrescrito abaixo se ativo

            for anchor_name, flow_var in node.hydraulic_ports().items():
                anchor = node.anchors.get(anchor_name)
                if anchor and flow_var in sol:
                    anchor.flow = sol[flow_var]


    def _mark_circuit_fault(self, circuit_pvars, anchor_to_pressure_var):
        # procura em TODOS os nodes do grafo, não só os do circuito
        for node in self.nodes.values():
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
                    anchor.pressure = "ERR"
                    anchor.flow = "ERR"
                    any_fault = True
                else:
                    all_fault = False

            if any_fault and all_fault:
                node.fault = True