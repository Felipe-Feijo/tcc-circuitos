"""Classes base do domínio de simulação: Node, Anchor e nós primitivos.

Define o contrato que todos os nós de simulação devem seguir e fornece
os dois nós mais simples do domínio pneumático — PressureSource e Exhaust —
que não justificam arquivos próprios pela trivialidade da implementação.
"""

from __future__ import annotations


class Anchor:
    def __init__(self, name: str, node: "Node", domain: str):
        self.node = node
        self.name = name
        self.domain = domain
        self.id = (node.id, name)
        self.connections: list["Connection"] = []

        self.state: bool = False
        self.is_driver: bool = False

        self.type: str | None = None
        self.pressure: float = 0.0
        self.flow: float = 0.0
        self.pressure_var: str | None = None
        self.fault = False
        self.pressurizing = False  # conservação de vazão ainda não atingida

    def connect(self, connection: "Connection"):
        if connection not in self.connections:
            self.connections.append(connection)


class Node:
    """Classe base para todos os nós do domínio de simulação.

    Subclasses declaram o atributo de classe `node_type` e chamam
    `super().__init__` antes de acessar `self.properties`.

    Contrato de simulação:
        update(outputs):          chamado a cada iteração até estabilizar.
        post_step_update(dt):     chamado uma vez após a convergência.
        handle_command(cmd):      recebe dicionário do sinal NodeItem.command.
        get_state() / set_state(): usados pelo HistoryManager (step_backward).
        get_internal_connections(): retorna [(anchor_a, anchor_b), ...].
    """

    def __init__(self, node_id: str, node_type: str, *,
                 domain: str | None = None,
                 properties: dict | None = None,
                 **kwargs):
        self.id = node_id
        self.type = node_type
        self.anchors: dict = {}
        self.domain: str | None = domain
        self.properties: dict = properties or {}

    def add_anchor(self, name, domain) -> Anchor:
        anchor = Anchor(name, self, domain)
        self.anchors[name] = anchor
        return anchor

    def get_anchor(self, name):
        return self.anchors[name]

    def get_state(self) -> dict:
        """Serializa o estado atual de todos os âncoras para snapshot.

        Returns:
            Dicionário com o estado de cada âncora, incluindo pressão e
            vazão para âncoras do domínio hidráulico.
        """
        anchors_state = {}
        for name, anchor in self.anchors.items():
            anchor_data = {"state": anchor.state}
            if anchor.domain == "hydraulic":
                anchor_data["pressure"] = anchor.pressure
                anchor_data["flow"]     = anchor.flow
                anchor_data["fault"]    = getattr(anchor, "fault", False)
            anchors_state[name] = anchor_data

        return {"anchors": anchors_state}

    def set_state(self, state: dict):
        """Restaura o estado dos âncoras a partir de um snapshot.

        Args:
            state: Dicionário no formato retornado por get_state().
        """
        for name, anchor_data in state.get("anchors", {}).items():
            anchor = self.anchors.get(name)
            if not anchor:
                continue
            anchor.state = anchor_data.get("state", anchor.state)
            if anchor.domain == "hydraulic":
                anchor.pressure = anchor_data.get("pressure", anchor.pressure)
                anchor.flow     = anchor_data.get("flow", anchor.flow)
                anchor.fault    = anchor_data.get("fault", False)

    def handle_command(self, command: str):
        """Recebe um comando externo (UI, teste ou debug). No-op por padrão."""
        pass

    def update(self, outputs=None):
        """Atualiza o estado interno do nó com base nas saídas da iteração anterior.

        Chamado pelo SimulationEngine a cada iteração até estabilização.
        Nós sem dinâmica própria não precisam sobrescrever este método.
        """
        pass

    def post_step_update(self, dt):
        """Executado uma única vez após a estabilização do passo.

        Utilizado para sensores, delays e commits de estado físico.

        Args:
            dt: Intervalo de tempo em segundos desde o último passo.
        """
        pass

    def get_internal_connections(self):
        """Retorna as conexões internas do nó entre seus próprios âncoras.

        Returns:
            Lista de tuplas (anchor_a, anchor_b). Retorna lista vazia por padrão.
        """
        return []

    def get_visual_state(self):
        return None


class PressureSource(Node):
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id=node_id, node_type="pressure_source", **kwargs)

    def update(self, outputs=None):
        self.get_anchor("P").state = True
        self.get_anchor("P").is_driver = True


class Exhaust(Node):
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id=node_id, node_type="exhaust", **kwargs)

    def update(self, outputs=None):
        self.get_anchor("R").state = False
        self.get_anchor("R").is_driver = True


class Junction(Node):
    """Nó de junção: ponto de derivação num fio/tubo, sem dinâmica própria.

    Único anchor, nome "J". O fan-out elétrico/hidráulico/pneumático
    acontece de graça -- `Anchor.connections` já é uma lista, então basta
    ligar 3+ Connections ao mesmo Anchor. Sem overrides: `update()` e
    `get_internal_connections()` herdados de Node já são no-op/[]."""

    def __init__(self, node_id, **kwargs):
        super().__init__(node_id=node_id, node_type="junction", **kwargs)
