"""Manages the step queue and the simulation's play/pause timer."""

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class StepScheduler(QObject):
    """Controls the queueing and firing of simulation steps.

    Responsibilities:
    - Queue step requests (request_step).
    - Drive the play/pause timer.
    - Emit step_requested when a step should run.

    Guarantees that only one step runs at a time: a new trigger only
    happens after mark_step_done() is called by the controller.

    Signals:
        step_requested: Emitted when a step should run.
    """

    step_requested = pyqtSignal()

    def __init__(self, timer_interval: int = 1000):
        super().__init__()
        self.pending_steps: int = 0
        self.step_in_progress: bool = False
        self.playing: bool = False

        self.timer_interval: int = timer_interval
        self._timer = QTimer()
        self._timer.timeout.connect(self._on_tick)

    # Public API

    def play(self) -> None:
        """Starts continuous execution via timer."""
        if self.playing:
            return
        self.playing = True
        self._timer.start(self.timer_interval)

    def pause(self) -> None:
        """Pauses continuous execution."""
        self.playing = False
        self._timer.stop()

    def request_step(self, n: int = 1, reset_timer: bool = False) -> None:
        """Queues n steps and tries to fire immediately.

        Args:
            n: Number of steps to queue.
            reset_timer: If True and playing, restarts the timer to avoid
                a double trigger after a manual command.
        """
        self.pending_steps += n
        if reset_timer and self.playing:
            self._timer.stop()
            self._timer.start(self.timer_interval)
        self._try_emit()

    def set_timer_interval(self, ms: int) -> None:
        """Updates the timer interval; restarts it if playing.

        Args:
            ms: New interval in milliseconds.
        """
        self.timer_interval = ms
        if self.playing:
            self._timer.stop()
            self._timer.start(ms)

    def mark_step_started(self) -> None:
        """Records that a step has started (blocks new triggers)."""
        self.step_in_progress = True

    def mark_step_done(self) -> None:
        """Records that the current step finished and tries to fire the next one."""
        self.step_in_progress = False
        self._try_emit()

    # Internal methods

    def _on_tick(self) -> None:
        """Timer callback: queues a step on every tick."""
        self.request_step(1)

    def _try_emit(self) -> None:
        """Emits step_requested if no step is in progress and steps are pending."""
        if self.step_in_progress or self.pending_steps <= 0:
            return
        self.pending_steps -= 1
        self.step_requested.emit()
