from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class StepScheduler(QObject):
    """Manages step queuing and the play/pause timer.

    Responsibilities:
    - Queue step requests (request_step)
    - Drive the play/pause timer
    - Emit step_requested when a step should actually execute
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

    # ── Public API ────────────────────────────────────────────────────────────

    def play(self) -> None:
        if self.playing:
            return
        self.playing = True
        self._timer.start(self.timer_interval)

    def pause(self) -> None:
        self.playing = False
        self._timer.stop()

    def request_step(self, n: int = 1, reset_timer: bool = False) -> None:
        """Queue n steps.  Optionally reset the play timer to avoid double-fire."""
        self.pending_steps += n
        if reset_timer and self.playing:
            self._timer.stop()
            self._timer.start(self.timer_interval)
        self._try_emit()

    def set_timer_interval(self, ms: int) -> None:
        self.timer_interval = ms
        if self.playing:
            self._timer.stop()
            self._timer.start(ms)

    def mark_step_started(self) -> None:
        self.step_in_progress = True

    def mark_step_done(self) -> None:
        self.step_in_progress = False
        self._try_emit()

    def can_step_back(self, history_len: int) -> bool:
        return history_len > 1

    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_tick(self) -> None:
        self.request_step(1)

    def _try_emit(self) -> None:
        if self.step_in_progress or self.pending_steps <= 0:
            return
        self.pending_steps -= 1
        self.step_requested.emit()