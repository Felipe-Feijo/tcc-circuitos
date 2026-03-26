from collections import defaultdict

from simulation.hydraulic_solver import NodeContinuity, NonlinearSystemSolver


class SimulationEngine:
    def __init__(self, nodes, connections, max_iterations=100000):
        self.nodes = nodes
        self.connections = connections
        self.max_iterations = max_iterations
        self.outputs = {}
        # Persistência dos NodeContinuity entre steps: pvar -> NodeContinuity
        self._continuities: dict[str, NodeContinuity] = {}
        self._prev_circuit_map = {}

    def run_until_stable(self, dt=0.1):
        iteration = 0

        while True:
            iteration += 1
            print(iteration)
            if iteration > self.max_iterations:
                raise RuntimeError(
                    f"Simulation did not stabilize after {self.max_iterations} iterations. "
                    "Possible feedback loop or invalid topology."
                )

            for node in self.nodes.values():
                node.update(self.outputs)

            changed = False
            changed |= self._update_pneumatic_domain()
            changed |= self._update_hydraulic_domain()
            changed |= self._update_electric_domain()

            if not changed:
                break

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
        queue = [start_anchor]
        domain = start_anchor.domain

        while queue:
            anchor = queue.pop(0)
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

        valid_anchors = set()
        for node in self.nodes.values():
            for source in node.anchors.values():
                if source.type == "source":
                    visited = set()
                    self._mark_valid_from_source(source, visited, valid_anchors)

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
        if anchor in visited:
            return False

        visited.add(anchor)

        if anchor.type == "ground":
            valid_anchors.add(anchor)
            visited.remove(anchor)
            return True

        reaches_ground = False

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

        for conn in anchor.connections:
            other = conn.get_other(anchor)
            if other and other.domain == "electric":
                if self._mark_valid_from_source(other, visited, valid_anchors):
                    reaches_ground = True

        visited.remove(anchor)

        if reaches_ground:
            valid_anchors.add(anchor)

        return reaches_ground

    # Pressão máxima antes de marcar circuito como fault
    P_MAX = 10_000

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

        old_pressures = {
            anchor: anchor.pressure
            for anchor, pvar in anchor_to_pressure_var.items()
            if pvar in circuit_pvars
        }

        # 🔥 NOVO: detectar mudança de topologia e resetar p_previous
        new_nodes_set = set(circuit_list)

        for pvar in circuit_pvars:
            prev_nodes = self._prev_circuit_map.get(pvar)

            if prev_nodes is not None and prev_nodes != new_nodes_set:
                cont = self._continuities.get(pvar)
                if cont:
                    cont.p_previous = 0.0

            # atualiza mapa
            self._prev_circuit_map[pvar] = new_nodes_set

        # ----------------------------
        # resolver circuito
        # ----------------------------
        sol = self._try_solve(index, circuit_list, anchor_to_pressure_var)

        if sol is None:
            for pvar, continuity in self._continuities.items():
                if pvar in circuit_pvars:
                    continuity.p_previous = 0.0
            self._mark_circuit_fault(circuit_pvars, anchor_to_pressure_var)
            return False

        # Verifica pressão máxima
        for pvar in circuit_pvars:
            if pvar in sol and abs(sol[pvar]) > self.P_MAX:
                print(f"circuito {index}: pressão {sol[pvar]:.2e} excede P_MAX={self.P_MAX}")
                for pvar2, continuity in self._continuities.items():
                    if pvar2 in circuit_pvars:
                        continuity.p_previous = 0.0
                self._mark_circuit_fault(circuit_pvars, anchor_to_pressure_var)
                return False

        # Atualiza p_previous
        for pvar, continuity in self._continuities.items():
            if pvar in circuit_pvars:
                continuity.update_pressure(sol)

        self._write_circuit_results(circuit_list, anchor_to_pressure_var, sol)

        changed = False
        for anchor, pvar in anchor_to_pressure_var.items():
            if pvar in sol:
                old_p = old_pressures.get(anchor)
                new_p = sol[pvar]
                old_val = old_p if not isinstance(old_p, str) else None
                tol_abs = 1e-6
                tol_rel = 1e-4

                if old_val is None:
                    changed = True
                    break
                else:
                    diff = abs(new_p - old_val)
                    scale = max(1.0, abs(new_p))

                    if diff > tol_abs and diff / scale > tol_rel:
                        changed = True
                        break

        return changed

    def _try_solve(self, index, circuit_list, anchor_to_pressure_var):
        from collections import defaultdict

        # ----------------------------
        # 1. Mapear flows por pressão
        # ----------------------------
        group_flows = defaultdict(list)
        for node in circuit_list:
            for anchor_name, flow_var in node.hydraulic_ports().items():
                anchor = node.anchors.get(anchor_name)
                if not anchor:
                    continue
                pvar = anchor_to_pressure_var.get(anchor)
                if pvar:
                    group_flows[pvar].append(flow_var)

        # ----------------------------
        # 2. Criar / atualizar continuities
        # ----------------------------
        continuities = []
        for pvar, flow_vars in group_flows.items():
            if pvar not in self._continuities:
                self._continuities[pvar] = NodeContinuity(pvar, flow_vars)
            else:
                self._continuities[pvar].flow_vars = flow_vars
            continuities.append(self._continuities[pvar])

        # ----------------------------
        # 3. Detectar p_set do circuito
        # ----------------------------
        psets = [
            getattr(node, "p_set", None)
            for node in circuit_list
            if hasattr(node, "p_set") and node.p_set is not None
        ]
        psets = [p for p in psets if p is not None]

        has_relief = len(psets) > 0
        min_pset = min(psets) if has_relief else None

        # ----------------------------
        # 4. Definir referência de vazão
        # ----------------------------
        Q_ref = next(
            (node.flow_hint for node in circuit_list
            if hasattr(node, "flow_hint") and node.flow_hint > 1e-10),
            1e-4
        )

        alpha = 0.6  # fração de subida desejada por iteração

        # ----------------------------
        # 5. Ajustar ZC por circuito
        # ----------------------------
        for cont in continuities:
            if has_relief:
                ZC_new = (alpha * min_pset) / Q_ref

                # clamp para evitar extremos
                ZC_new = max(1e3, min(ZC_new, 1e7))

                # opcional: estabilizar perto do regime
                if cont.p_previous > 0.9 * min_pset:
                    cont.ZC = 1e4
                else:
                    cont.ZC = ZC_new
            else:
                cont.ZC = 1e4

        # ----------------------------
        # 6. Criar solver
        # ----------------------------
        solver = NonlinearSystemSolver(circuit_list + continuities)
        x0 = solver.build_initial_guess(circuit_list)

        # ----------------------------
        # 7. Inicializar pressões
        # ----------------------------
        for cont in continuities:
            pvar = cont.pressure_var
            if pvar in solver.var_index:
                x0[pvar] = cont.p_previous

        # ----------------------------
        # 8. Predição de pressão (agora SIM relevante)
        # ----------------------------
        if has_relief:
            for cont in continuities:
                pvar = cont.pressure_var
                P_prev = cont.p_previous

                P_pred = min_pset

                if pvar in solver.var_index:
                    x0[pvar] = P_pred

        else:
            for cont in continuities:
                pvar = cont.pressure_var
                P_prev = cont.p_previous

                P_pred = P_prev + cont.ZC * Q_ref

                if pvar in solver.var_index:
                    x0[pvar] = P_pred

        # ----------------------------
        # 9. (opcional) ajudar a abrir relief
        # ----------------------------
        if has_relief:
            for node in circuit_list:
                if hasattr(node, "p_set"):
                    try:
                        x0[node.flow_var_in] = Q_ref
                    except Exception:
                        pass

        # ----------------------------
        # 10. Resolver
        # ----------------------------
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
        for anchor, pvar in anchor_to_pressure_var.items():
            if pvar in sol:
                anchor.pressure = sol[pvar]
                anchor.fault = False

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

    def _mark_circuit_fault(self, circuit_pvars, anchor_to_pressure_var):
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
