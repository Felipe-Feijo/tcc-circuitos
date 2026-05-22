"""Sincroniza o estado de domínio de volta aos itens gráficos após cada passo."""


class ViewSync:
    """Empurra o estado de domínio para os itens gráficos após cada passo.

    Desacoplado de QObject — não usa sinais, apenas chamadas diretas de método.

    Attributes:
        node_map: Mapeamento de NodeItem para o nó de domínio correspondente.
        connection_map: Mapeamento de ConnectionItem para a conexão de domínio.
    """

    def __init__(self):
        self.node_map: dict = {}
        self.connection_map: dict = {}

    def sync(self) -> None:
        """Atualiza visualmente todos os itens gráficos com o estado de domínio atual.

        Chama update_from_domain em cada NodeItem e set_state em cada ConnectionItem.
        """
        for node_item, domain_node in self.node_map.items():
            node_item.update_from_domain(domain_node)

        for conn_item, domain_conn in self.connection_map.items():
            conn_item.set_state(domain_conn.get_state())
