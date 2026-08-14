"""Constrói o grafo de simulação a partir dos itens gráficos da cena."""

from simulation.connections import Connection


class GraphBuilder:
    """Converte itens gráficos da cena em nós e conexões do domínio de simulação.

    Uso típico pelo EditorController:
        builder = GraphBuilder()
        builder.add_node_from_item(node_item)       # para cada NodeItem
        builder.add_connection_from_item(conn_item) # para cada ConnectionItem
        builder.raise_if_errors()
    """

    def __init__(self):
        self.nodes: dict = {}
        self.connections: dict = {}
        self.node_map: dict = {}
        self.connection_map: dict = {}
        self._errors: list[str] = []

    def add_node_from_item(self, node_item):
        """Cria o nó de domínio correspondente a um NodeItem gráfico.

        Args:
            node_item: Instância de NodeItem presente na cena.

        Returns:
            O nó de domínio criado, ou None se a criação falhar por
            propriedades obrigatórias ausentes (o erro é acumulado
            internamente e pode ser lançado via raise_if_errors).

        Raises:
            ValueError: Se a subclasse de NodeItem não declarar simulation_cls.
        """
        node_cls = node_item.simulation_cls
        if node_cls is None:
            raise ValueError(
                f"{type(node_item).__name__} não define 'simulation_cls'. "
                "Declare o atributo de classe na subclasse de NodeItem."
            )

        try:
            node = node_cls(
                node_item.id,
                domain=node_item.domain,
                properties=getattr(node_item, "properties", {}),
            )
        except ValueError as e:
            self._errors.append(str(e))
            return None

        anchor_items = (
            node_item.anchor_list
            if hasattr(node_item, "anchor_list")
            else node_item.anchors.values()
        )

        for anchor_item in anchor_items:
            node.add_anchor(name=anchor_item.name, domain=anchor_item.domain)

        self.nodes[node.id] = node
        self.node_map[node_item] = node
        return node

    def add_connection_from_item(self, connection_item):
        """Cria a conexão de domínio correspondente a um ConnectionItem gráfico.

        Args:
            connection_item: Instância de ConnectionItem presente na cena.

        Returns:
            A Connection de domínio criada, ou None se um dos nós ligados
            a esta conexão falhou ao ser criado (propriedade obrigatória
            ausente -- o erro já foi acumulado por add_node_from_item e
            será reportado por raise_if_errors(); não há nó pra conectar).
        """
        source_anchor_item = connection_item.source_anchor
        target_anchor_item = connection_item.target_anchor

        source_node = self.nodes.get(source_anchor_item.node.id)
        target_node = self.nodes.get(target_anchor_item.node.id)
        if source_node is None or target_node is None:
            return None

        source_anchor = source_node.get_anchor(source_anchor_item.name)
        target_anchor = target_node.get_anchor(target_anchor_item.name)

        connection = Connection(source_anchor, target_anchor)

        if connection.id not in self.connections:
            self.connections[connection.id] = connection
            self.connection_map[connection_item] = connection

        return self.connections[connection.id]

    def raise_if_errors(self) -> None:
        """Lança ValueError consolidado se algum nó tiver propriedades obrigatórias ausentes.

        Raises:
            ValueError: Mensagem combinada de todos os erros acumulados.
        """
        if self._errors:
            raise ValueError("\n".join(self._errors))
