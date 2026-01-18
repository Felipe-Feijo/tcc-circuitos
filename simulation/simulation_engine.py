class SimulationEngine:
    def __init__(self, nodes, connections):
        self.nodes = nodes          # dict[id, Node]
        self.connections = connections

    def run_until_stable(self):
        changed = True

        while changed:
            changed = False

            # 1. Atualiza FSMs
            for node in self.nodes.values():
                old_state = getattr(node, "state", None)
                node.update()  # PressureSource e Exhaust podem setar anchors como drivers
                if getattr(node, "state", None) != old_state:
                    changed = True

            # 2. Propagação de pressão
            visited = set()
            for node in self.nodes.values():
                for anchor in node.anchors.values():
                    if anchor in visited:
                        continue
                    # BFS para encontrar todo grupo conectado
                    group = self._get_connected_group(anchor)
                    visited.update(group)

                    # Coletar drivers
                    drivers = [a for a in group if a.is_driver]

                    if not drivers:
                        continue  # sem drivers, nada muda

                    # AND lógico de todos os drivers
                    group_state = all(d.pressurized for d in drivers)

                    # Aplicar aos não-drivers
                    for a in group:
                        if not a.is_driver:
                            if a.pressurized != group_state:
                                a.pressurized = group_state
                                changed = True

    def _get_connected_group(self, start_anchor):
        """BFS para coletar todos anchors conectados direta ou indiretamente."""
        group = set()
        queue = [start_anchor]

        while queue:
            anchor = queue.pop(0)
            if anchor in group:
                continue
            group.add(anchor)
            # Adiciona conexões internas do node
            for a_id, b_id in anchor.node.get_internal_connections():
                a_anchor = anchor.node.get_anchor(a_id)
                b_anchor = anchor.node.get_anchor(b_id)
                if a_anchor == anchor and b_anchor not in group:
                    queue.append(b_anchor)
                elif b_anchor == anchor and a_anchor not in group:
                    queue.append(a_anchor)
            # Adiciona conexões externas
            for conn in anchor.connections:
                other = conn.get_other(anchor)
                if other not in group:
                    queue.append(other)
        return group