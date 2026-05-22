"""Orquestra a execução da simulação, delegando a três módulos focados."""

import logging
from PyQt6.QtCore import QObject, pyqtSignal
from simulation.simulation_engine import SimulationEngine
from simulation.step_scheduler import StepScheduler
from simulation.view_sync import ViewSync
from simulation.history_manager import HistoryManager

logger = logging.getLogger(__name__)


class SimulationController(QObject):
    """Orquestra uma simulação em execução.

    Delega responsabilidades a três módulos especializados:
      StepScheduler   — timer, play/pause, fila de passos.
      ViewSync        — empurra estado de domínio para os itens gráficos.
      HistoryManager  — snapshots para step_backward.

    A API pública é compatível com a versão anterior monolítica,
    portanto SimulationSession e o código de UI não precisam de alterações.

    Signals:
        state_changed: Emitido após cada passo ou ação que altera o estado.
    """

    state_changed = pyqtSignal()

    def __init__(self, engine: SimulationEngine, max_history: int = 5):
        super().__init__()

        self.engine = engine
        self.dt: float = 0.1

        self._scheduler = StepScheduler()
        self._scheduler.step_requested.connect(self._execute_step)

        self._view_sync = ViewSync()
        self._history = HistoryManager(max_history)

    # Propriedades de compatibilidade (lidas diretamente por Session e UI)

    @property
    def playing(self) -> bool:
        return self._scheduler.playing

    @property
    def timer_interval(self) -> int:
        return self._scheduler.timer_interval

    @timer_interval.setter
    def timer_interval(self, value: int) -> None:
        self._scheduler.timer_interval = value

    @property
    def on_update_node(self) -> dict:
        return self._view_sync.node_map

    @on_update_node.setter
    def on_update_node(self, value: dict) -> None:
        self._view_sync.node_map = value or {}

    @property
    def on_update_connection(self) -> dict:
        return self._view_sync.connection_map

    @on_update_connection.setter
    def on_update_connection(self, value: dict) -> None:
        self._view_sync.connection_map = value or {}

    # API pública

    def play(self) -> None:
        """Inicia a execução contínua por timer."""
        self._scheduler.play()

    def pause(self) -> None:
        """Pausa a execução contínua."""
        self._scheduler.pause()

    def set_dt(self, dt: float) -> None:
        """Define o intervalo de tempo entre passos de simulação."""
        self.dt = dt

    def set_timer_interval(self, ms: int) -> None:
        """Define o intervalo do timer de play em milissegundos."""
        self._scheduler.set_timer_interval(ms)

    def request_step(self, n: int = 1, reset_timer: bool = False) -> None:
        """Enfileira n passos de simulação.

        Args:
            n: Número de passos a enfileirar.
            reset_timer: Se True e em play, reinicia o timer para evitar
                disparo duplo após um comando manual.
        """
        self._scheduler.request_step(n, reset_timer=reset_timer)

    def command(self, node_id: str, cmd: dict) -> None:
        """Recebe um comando de um NodeItem e o repassa ao nó de domínio.

        Args:
            node_id: Identificador do nó que emitiu o comando.
            cmd: Dicionário de payload (ex: {"action": "toggle"}).
        """
        node = self.engine.nodes.get(node_id)
        if not node:
            logger.warning("command: nó %s não encontrado", node_id)
            return
        node.handle_command(cmd)
        self._scheduler.request_step(1, reset_timer=True)

    def step_forward(self) -> bool:
        """Executa um passo manualmente (somente se pausado).

        Returns:
            True se o passo foi enfileirado, False se em play.
        """
        if self._scheduler.playing:
            return False
        self._scheduler.request_step(1)
        return True

    def step_backward(self) -> bool:
        """Restaura o snapshot anterior (somente se pausado).

        Returns:
            True se a restauração ocorreu, False se em play ou sem histórico.
        """
        if self._scheduler.playing:
            return False
        if not self._history.can_go_back():
            return False
        self._history.pop_and_restore(self.engine.nodes)
        self.engine.compute_outputs(dt=0)
        self._view_sync.sync()
        self.state_changed.emit()
        return True

    def can_step_back(self) -> bool:
        """Retorna True se há histórico disponível para step_backward."""
        return self._history.can_go_back()

    # Método interno

    def _execute_step(self) -> None:
        """Executa um passo de simulação: engine → view sync → histórico."""
        self._scheduler.mark_step_started()
        logger.debug("passo de simulação iniciado")
        try:
            self.engine.run_until_stable(dt=self.dt)
            self._view_sync.sync()
            self._history.push(self.engine.nodes)
        except Exception:
            logger.exception("erro durante o passo de simulação")
        finally:
            logger.debug("passo de simulação concluído")
            self._scheduler.mark_step_done()
            self.state_changed.emit()
