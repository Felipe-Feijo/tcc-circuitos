"""Main simulation engine: iterates the three domains until stable.

SimulationEngine knows nothing about Qt or graphics items. It receives a
graph of domain nodes and connections and, on each run_until_stable()
call, propagates state across the pneumatic, electric and hydraulic
domains until no anchor changes value -- or until the iteration limit
is reached.
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
    """Multi-domain simulation engine based on fixed-point iteration.

    Iterates over the three domains (pneumatic, electric, hydraulic) in
    sequence until no anchor changes state -- indicating stabilization.
    The hydraulic domain uses an internal nonlinear solver with
    convergence detection and scale management.

    Args:
        nodes: {node_id: Node} dict built by the GraphBuilder.
        connections: {connection_id: Connection} dict.
        max_iterations: Fixed-point iteration limit before raising RuntimeError.
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
        """Runs fixed-point iterations until all three domains stabilize.

        On each iteration, calls node.update() on every node and
        propagates state across the pneumatic, electric and hydraulic
        domains. Stops when no domain reports a change. Once stable,
        calls compute_outputs().

        Args:
            dt: Time interval in seconds for post_step_update.

        Raises:
            RuntimeError: If the iteration count exceeds max_iterations.
        """
        iteration = 0

        if not self.outputs:
            # Seeds engine.outputs with the nodes' initial outputs (e.g.
            # cylinder sensors based on default_state) so the first
            # update already receives correct values instead of outputs={}.
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
        """Collects every node's outputs after stabilization.

        Calls post_step_update(dt) on each node and aggregates
        node.outputs values into self.outputs, used as input for the
        next run_until_stable iteration.

        Args:
            dt: Time interval in seconds since the last step.
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
        """Determines which electric anchors sit on some source->ground path.

        An anchor is "energized" if there's some simple path from a
        "source"-type anchor to a "ground"-type anchor passing through
        it -- being in the same connected component isn't enough (a
        dead-end branch hanging off the middle of the path doesn't
        conduct).

        Computed in O(V+E) via bridges (Tarjan): collapses each
        2-edge-connected component (e.g. two parallel contacts that
        reconverge) into a single node, and resolves "is it between a
        source and a ground?" with a single DP pass over the resulting
        bridge tree -- without re-exploring the same graph sub-region
        more than once.
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
        """Tarjan: edges whose removal disconnects the graph (low-link)."""
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
        """Merges anchors linked by edges that are NOT bridges (union-find)."""
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
        """Marks components sitting between a source and a ground in the bridge tree."""
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
        """DP over a bridge tree: sums sources/grounds per subtree and
        decides, per component, whether two distinct "arms" (local or
        neighboring) together cover a source and a ground."""
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
                # Source and ground fall in the same 2-edge-connected
                # block (e.g. two independent contacts of the same relay
                # closed at the same time, each completing a
                # source->ground path via a different route) -- current
                # closes within the block itself, no distinct external
                # "arms" needed.
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
        """Delegates the check to the ConvergenceMonitor."""
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
                "hydraulic domain did not converge after %d iterations.",
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

            # Includes all of the node's physical ports in the
            # connectivity graph (not just the active ones). A
            # directional valve has blocked ports that are still wired
            # up -- without this, the pump ends up in a separate circuit
            # from the cylinder when the valve commutates.
            # Note: this only affects the PARTITION (who's in the same
            # circuit), not the equations -- blocked ports never enter the solve.
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

        # dead circuit -- doesn't even call the solver.
        # Criterion: no node has is_flow_source=True, i.e. there's no
        # active flow source (pump running, cylinder with a compressed spring).
        # Decoupled from flow_hint so the ScaleManager can use flow_hint
        # as a pure order of magnitude without carrying state semantics.
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

        # active circuit -- checks for a topology change
        for pvar in circuit_pvars:
            prev_nodes = self._prev_circuit_map.get(pvar)
            if prev_nodes is not None and prev_nodes != new_nodes_set:
                # Topology change detected (a valve commutated, a
                # cylinder hit an end stop, etc). Instead of zeroing
                # p_previous (which would throw the solver to the
                # trivial point and cause dozens of least_squares
                # iterations until zc scales up), re-seeds with p_ref --
                # the same guess used when the NodeContinuity was created.
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

        # Only updates the scale memory if the solution is physically
        # valid. A spurious solution (bad flow balance) shouldn't "teach"
        # the ScaleManager -- otherwise an absurd q_ref could contaminate
        # subsequent solves via the EMA.
        _, q_ref_check = self._scale_manager.estimate(circuit_list)
        sol_q_values = [abs(v) for k, v in sol.items()
                        if k.startswith("Q_") and isinstance(v, float)]
        max_q = max(sol_q_values) if sol_q_values else 0.0
        q_is_sane = max_q < q_ref_check * 1e3   # at most 1000x the expected q_ref
        p_values_sol = [v for k, v in sol.items()
                        if k.startswith("P_") and isinstance(v, float) and v >= 0]
        max_p = max(p_values_sol) if p_values_sol else 0.0
        p_is_sane = max_p < self.P_MAX

        if q_is_sane and p_is_sane:
            self._scale_manager.update_from_solution(sol)
        else:
            logger.debug(
                "solution rejected by ScaleManager: max_q=%.2e, max_p=%.2e",
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

        # the circuit's p_ref -- used to seed new NodeContinuity instances
        circuit_p_ref = ctx.p_ref

        continuities = []
        for pvar, flow_vars in group_flows.items():
            if pvar not in self._continuities:
                cont = NodeContinuity(pvar, flow_vars)
                # Initial seed: uses the circuit's p_ref as the pressure
                # guess. Without this, p_previous=0 makes the solver
                # converge to the trivial point (everything at zero)
                # instead of the real steady state. The solver refines
                # from here -- it isn't a fixed value.
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
    print(f"  CIRCUIT {index}")
    print(SEP)

    # pressures per pressure node
    pvars_seen = set()
    print("\n  PRESSURES:")
    for anchor, pvar in anchor_to_pressure_var.items():
        if pvar in sol and pvar not in pvars_seen:
            pvars_seen.add(pvar)
            print(f"    {pvar:45s} = {sol[pvar]:+.4e} Pa")

    # flows per component
    print("\n  FLOWS:")
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