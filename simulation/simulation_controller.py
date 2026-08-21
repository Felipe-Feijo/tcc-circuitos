"""Orchestrates simulation execution, delegating to three focused modules."""

import logging
from PyQt6.QtCore import QObject, pyqtSignal
from simulation.simulation_engine import SimulationEngine
from simulation.step_scheduler import StepScheduler
from simulation.view_sync import ViewSync
from simulation.history_manager import HistoryManager

logger = logging.getLogger(__name__)


class SimulationController(QObject):
    """Orchestrates a running simulation.

    Delegates responsibilities to three specialized modules:
      StepScheduler   -- timer, play/pause, step queue.
      ViewSync        -- pushes domain state to the graphics items.
      HistoryManager  -- snapshots for step_backward.

    The public API is compatible with the previous monolithic version,
    so SimulationSession and the UI code need no changes.

    Signals:
        state_changed: Emitted after each step or action that changes state.
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

    # Compatibility properties (read directly by Session and the UI)

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

    # Public API

    def play(self) -> None:
        """Starts continuous execution via timer."""
        self._scheduler.play()

    def pause(self) -> None:
        """Pauses continuous execution."""
        self._scheduler.pause()

    def set_dt(self, dt: float) -> None:
        """Sets the time interval between simulation steps."""
        self.dt = dt

    def set_timer_interval(self, ms: int) -> None:
        """Sets the play timer interval in milliseconds."""
        self._scheduler.set_timer_interval(ms)

    def request_step(self, n: int = 1, reset_timer: bool = False) -> None:
        """Queues n simulation steps.

        Args:
            n: Number of steps to queue.
            reset_timer: If True and playing, restarts the timer to avoid
                a double trigger after a manual command.
        """
        self._scheduler.request_step(n, reset_timer=reset_timer)

    def command(self, node_id: str, cmd: dict) -> None:
        """Receives a command from a NodeItem and forwards it to the domain node.

        Args:
            node_id: Identifier of the node that emitted the command.
            cmd: Payload dict (e.g. {"action": "toggle"}).
        """
        node = self.engine.nodes.get(node_id)
        if not node:
            logger.warning("command: node %s not found", node_id)
            return
        node.handle_command(cmd)
        self._scheduler.request_step(1, reset_timer=True)

    def step_forward(self) -> bool:
        """Executes a step manually (only if paused).

        Returns:
            True if the step was queued, False if playing.
        """
        if self._scheduler.playing:
            return False
        self._scheduler.request_step(1)
        return True

    def step_backward(self) -> bool:
        """Restores the previous snapshot (only if paused).

        Returns:
            True if the restore happened, False if playing or with no history.
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
        """Returns True if history is available for step_backward."""
        return self._history.can_go_back()

    # Internal method

    def _execute_step(self) -> None:
        """Executes a simulation step: engine -> view sync -> history."""
        self._scheduler.mark_step_started()
        logger.debug("simulation step started")
        try:
            self.engine.run_until_stable(dt=self.dt)
            self._view_sync.sync()
            self._history.push(self.engine.nodes)
        except Exception:
            logger.exception("error during simulation step")
        finally:
            logger.debug("simulation step finished")
            self._scheduler.mark_step_done()
            self.state_changed.emit()
