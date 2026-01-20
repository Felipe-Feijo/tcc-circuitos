class SimulationEngine:
    def __init__(self, nodes, connections):
        self.nodes = nodes          # dict[id, Node]
        self.connections = connections

    def run_until_stable(self):
        """
        Resolve o sistema até que nenhum Anchor.pressurized mude.
        Mudanças internas de Node (FSM, temporizadores, posição, etc.)
        NÃO impedem estabilização.
        """
        changed = True

        while changed:
            changed = False

            # 1. Atualiza lógica interna dos nodes
            #    (pode alterar conectividade interna)
            for node in self.nodes.values():
                node.update()

            # 2. Propagação de pressão (anchor-driven)
            visited = set()

            for node in self.nodes.values():
                for anchor in node.anchors.values():
                    if anchor in visited:
                        continue

                    # BFS para encontrar todo grupo conectado
                    group = self._get_connected_group(anchor)
                    visited.update(group)

                    # Coletar drivers do grupo
                    drivers = [a for a in group if a.is_driver]

                    if not drivers:
                        continue  # sem drivers, nada a propagar

                    # AND lógico de todos os drivers
                    group_state = all(d.pressurized for d in drivers)

                    # Aplicar estado aos não-drivers
                    for a in group:
                        if a.is_driver:
                            continue

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

            # Conexões internas do node (dependem do estado atual)
            for a_id, b_id in anchor.node.get_internal_connections():
                a_anchor = anchor.node.get_anchor(a_id)
                b_anchor = anchor.node.get_anchor(b_id)

                if a_anchor == anchor and b_anchor not in group:
                    queue.append(b_anchor)
                elif b_anchor == anchor and a_anchor not in group:
                    queue.append(a_anchor)

            # Conexões externas
            for conn in anchor.connections:
                other = conn.get_other(anchor)
                if other not in group:
                    queue.append(other)

        return group
