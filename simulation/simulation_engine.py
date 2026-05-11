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


class SimulationEngine:
    def __init__(self, nodes, connections, max_iterations=100000):
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
        iteration = 0

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
            print(f"Hydraulic domain did not converge after {self._hydraulic_max_iterations} iterations.")
            return False

        return True

    def _collect_hydraulic_nodes(self) -> list:
            return [n for n in self.nodes.values() if isinstance(n, HydraulicNode)]

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

        # circuito morto — nem chama o solver
        if ctx.q_ref < 1e-10:
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
                self._reset_continuity(pvar)
            self._prev_circuit_map[pvar] = new_nodes_set

        sol = self._try_solve(index, circuit_list, anchor_to_pressure_var, ctx=ctx)

        if debug and sol:
            _print_circuit_state(index, circuit_list, anchor_to_pressure_var, sol)

        if sol is None:
            self._reset_circuit_continuities(circuit_pvars)
            self._mark_circuit_fault(circuit_list, circuit_pvars, anchor_to_pressure_var)
            return

        for pvar in circuit_pvars:
            if pvar in sol and abs(sol[pvar]) > self.P_MAX:
                self._reset_circuit_continuities(circuit_pvars)
                self._mark_circuit_fault(circuit_list, circuit_pvars, anchor_to_pressure_var)
                return

        for pvar, continuity in self._continuities.items():
            if pvar in circuit_pvars:
                continuity.update_pressure(sol)

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

        continuities = []
        for pvar, flow_vars in group_flows.items():
            if pvar not in self._continuities:
                self._continuities[pvar] = NodeContinuity(pvar, flow_vars)
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
            print(f"  circuito {index}: falhou — {e}")
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