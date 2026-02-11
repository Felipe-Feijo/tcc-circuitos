class SimulationEngine:
    def __init__(self, nodes, connections, max_iterations=100):
        self.nodes = nodes          # dict[id, Node]
        self.connections = connections
        self.max_iterations = max_iterations   

        self.outputs = {}        # dict[name, payload] 

    def run_until_stable(self):
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
        self.compute_outputs()
        
    def compute_outputs(self):
        self.outputs = {}

        for node in self.nodes.values():
            node.post_step_update()

            node_outputs = getattr(node, "outputs", None)
            if not node_outputs:
                continue

            for name, payload in node_outputs.items():
                self.outputs[name] = payload
        print("outputs:", self.outputs)


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
    
    def _get_connected_group(self, start_anchor):
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
        changed = False
        for node in self.nodes.values():
            for a in node.anchors.values():
                if a.domain != "electric": continue
                a.voltage = 0  # reset

        for node in self.nodes.values():
            for source in node.anchors.values():
                if source.type != "source": continue
                # BFS até encontrar grounds
                closed_circuit_anchors = self._find_closed_circuits(source)
                for a in closed_circuit_anchors:
                    if a.voltage != source.voltage:
                        a.voltage = source.voltage
                        changed = True

        return changed

    def _find_closed_circuits(self, source):
        """Retorna anchors que estão em circuito fechado source → ground"""
        visited = set()
        queue = [(source, [source])]  # anchor + caminho atual
        closed_circuit_anchors = set()

        while queue:
            anchor, path = queue.pop(0)
            if anchor in visited:
                continue
            visited.add(anchor)

            if anchor.type == "ground":
                # marca todo o caminho como fechado
                closed_circuit_anchors.update(path)
                continue

            for conn in anchor.connections:
                other = conn.get_other(anchor)
                if other.domain != "electric": continue
                if other not in visited:
                    queue.append((other, path + [other]))

        return closed_circuit_anchors
    
    def _update_hydraulic_domain(self):
        """
        Placeholder for hydraulic propagation.
        """
        return False