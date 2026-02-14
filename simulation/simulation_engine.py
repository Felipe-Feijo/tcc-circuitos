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
        """
        Placeholder for hydraulic propagation.
        """
        return False