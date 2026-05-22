"""Gerencia o ciclo de vida de uma sessão de simulação."""

from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.node_item import NodeItem
from editor.editor_controller import EditorController
from simulation.simulation_engine import SimulationEngine
from simulation.simulation_controller import SimulationController


class SimulationSession:
    """Controla o ciclo de vida completo de uma simulação.

    Responsabilidades:
    - Construir o grafo de domínio a partir da cena gráfica atual.
    - Criar e possuir SimulationEngine e SimulationController.
    - Ligar e desligar os itens gráficos à simulação.
    - Expor play/pause/toggle para a UI sem expor os detalhes internos.

    Configurações de dt, timer_interval e speed_index persistem entre
    sessões (início/parada) e são restauradas a cada novo start().
    """

    def __init__(self, scene):
        self.scene = scene
        self.engine = None
        self.controller = None
        self.active = False

        # Configurações persistentes entre sessões
        self.dt = 0.1
        self.timer_interval = 1000
        self.speed_index = 0

    def start(self) -> str | None:
        """Inicia a simulação a partir do estado atual da cena.

        Constrói o grafo de domínio, instancia o engine e o controller,
        vincula os itens gráficos e executa o primeiro passo.

        Returns:
            None se iniciado com sucesso, ou uma string de erro se algum
            componente tiver propriedades obrigatórias não preenchidas.
            O chamador é responsável por exibir a mensagem ao usuário.
        """
        if self.active:
            return None

        # Passo 1: constrói o grafo de domínio
        editor = EditorController(self.scene)
        builder = editor.build_graph()

        # Passo 2: cria o engine — lança ValueError se props obrigatórias faltam
        try:
            builder.raise_if_errors()
            self.engine = SimulationEngine(
                nodes=builder.nodes,
                connections=builder.connections,
            )
        except ValueError as e:
            return str(e)

        self.controller = SimulationController(self.engine)
        self.controller.on_update_node = builder.node_map
        self.controller.on_update_connection = builder.connection_map

        # Restaura configurações persistentes
        self.controller.set_dt(self.dt)
        self.controller.timer_interval = self.timer_interval

        self.active = True

        # Passo 3: ativa os itens gráficos no modo simulação
        self._activate_node_items()

        # Passo 4: executa o primeiro passo para semear o estado visual
        self.controller.request_step(1)
        return None

    def stop(self):
        """Para a simulação e restaura o estado visual dos itens gráficos."""
        if not self.active:
            return

        self._deactivate_node_items()

        self.engine = None
        self.controller = None
        self.active = False

    def play(self):
        """Inicia a execução contínua por timer."""
        if not self.active:
            return
        self.controller.play()

    def pause(self):
        """Pausa a execução contínua."""
        if not self.active:
            return
        self.controller.pause()

    def toggle_play(self):
        """Alterna entre play e pause."""
        if not self.active:
            return
        if self.controller.playing:
            self.controller.pause()
        else:
            self.controller.play()

    def is_playing(self) -> bool:
        """Retorna True se a simulação estiver rodando continuamente."""
        return bool(self.active and self.controller and self.controller.playing)

    # Métodos internos

    def _activate_node_items(self):
        """Coloca todos os NodeItems da cena em modo simulação."""
        for item in self.scene.items():
            if not isinstance(item, NodeItem):
                continue
            item.simulation_mode = True
            item.on_simulation_activated()
            item.command.connect(self.controller.command)

    def _deactivate_node_items(self):
        """Restaura o estado visual dos itens e desconecta sinais de comando."""
        for item in self.scene.items():
            if isinstance(item, NodeItem):
                item.reset_visual_state()
                try:
                    item.command.disconnect(self.controller.command)
                except TypeError:
                    pass  # sinal já desconectado ou nunca conectado
            elif isinstance(item, ConnectionItem):
                item.reset_visual_state()
