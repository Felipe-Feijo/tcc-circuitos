import logging
from PyQt6.QtCore import QObject, pyqtSignal
from simulation.simulation_engine import SimulationEngine
from simulation.step_scheduler import StepScheduler
from simulation.view_sync import ViewSync
from simulation.history_manager import HistoryManager

logger = logging.getLogger(__name__)


class SimulationController(QObject):
    """Orchestrates a running simulation.

    Delegates to three focused helpers:
      StepScheduler   — timer, play/pause, step queue
      ViewSync        — push domain state into graphical items
      HistoryManager  — snapshots for step_backward

    The public API is unchanged from the previous monolithic version so
    SimulationSession and UI code require no updates.
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

    # ── Compatibility properties (Session / UI read these directly) ──────────

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

    # ── Public API ───────────────────────────────────────────────────────────

    def play(self) -> None:
        self._scheduler.play()

    def pause(self) -> None:
        self._scheduler.pause()

    def set_dt(self, dt: float) -> None:
        self.dt = dt

    def set_timer_interval(self, ms: int) -> None:
        self._scheduler.set_timer_interval(ms)

    def request_step(self, n: int = 1, reset_timer: bool = False) -> None:
        self._scheduler.request_step(n, reset_timer=reset_timer)

    def command(self, node_id: str, cmd: dict) -> None:
        node = self.engine.nodes.get(node_id)
        if not node:
            logger.warning("command: node %s not found", node_id)
            return
        node.handle_command(cmd)
        self._scheduler.request_step(1, reset_timer=True)

    def step_forward(self) -> bool:
        if self._scheduler.playing:
            return False
        self._scheduler.request_step(1)
        return True

    def step_backward(self) -> bool:
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
        return self._history.can_go_back()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _execute_step(self) -> None:
        self._scheduler.mark_step_started()
        logger.debug("simulation step started")
        try:
            self.engine.run_until_stable(dt=self.dt)
            self._view_sync.sync()
            self._history.push(self.engine.nodes)
        except Exception:
            logger.exception("error during simulation step")
        finally:
            logger.debug("simulation step done")
            self._scheduler.mark_step_done()
            self.state_changed.emit()
