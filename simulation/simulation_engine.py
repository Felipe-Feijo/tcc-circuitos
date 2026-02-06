class SimulationEngine:
    def __init__(self, nodes, connections, max_iterations=100):
        self.nodes = nodes          # dict[id, Node]
        self.connections = connections
        self.max_iterations = max_iterations   

        self.outputs = {}        # dict[name, payload] 

    def run_until_stable(self):
        """
        Resolve until no Anchor.pressurized changes.
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
            # Update internal node logic
            for node in self.nodes.values():
                node.update(self.outputs)

            # Propagate pressure through connected anchor groups
            visited = set()
            changed = False

            for node in self.nodes.values():
                for anchor in node.anchors.values():
                    if anchor in visited:
                        continue

                    # Get all connected anchors
                    group = self._get_connected_group(anchor)
                    visited.update(group)

                    # Collect drivers and compute group state (AND logic)
                    drivers = [a for a in group if a.is_driver]
                    if not drivers:
                        continue

                    group_state = all(d.pressurized for d in drivers)

                    # Apply state to non-drivers
                    for a in group:
                        if not a.is_driver and a.pressurized != group_state:
                            a.pressurized = group_state
                            changed = True

            if not changed:
                break

        # 🔹 3. Pós-step (fora do loop de estabilização!)
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

    def _get_connected_group(self, start_anchor):
        """BFS to collect all directly or indirectly connected anchors."""
        group = set()
        queue = [start_anchor]

        while queue:
            anchor = queue.pop(0)
            if anchor in group:
                continue
            group.add(anchor)

            # Internal node connections (state-dependent)
            for a_id, b_id in anchor.node.get_internal_connections():
                a_anchor = anchor.node.get_anchor(a_id)
                b_anchor = anchor.node.get_anchor(b_id)
                
                other = b_anchor if a_anchor == anchor else a_anchor if b_anchor == anchor else None
                if other and other not in group:
                    queue.append(other)

            # External connections
            for conn in anchor.connections:
                other = conn.get_other(anchor)
                if other not in group:
                    queue.append(other)

        return group