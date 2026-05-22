"""Gerencia a fila de passos e o timer de play/pause da simulação."""

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class StepScheduler(QObject):
    """Controla o enfileiramento e o disparo dos passos de simulação.

    Responsabilidades:
    - Enfileirar requisições de passo (request_step).
    - Conduzir o timer de play/pause.
    - Emitir step_requested quando um passo deve ser executado.

    Garante que apenas um passo seja executado por vez: um novo disparo
    só ocorre após mark_step_done() ser chamado pelo controller.

    Signals:
        step_requested: Emitido quando um passo deve ser executado.
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

    # API pública

    def play(self) -> None:
        """Inicia a execução contínua por timer."""
        if self.playing:
            return
        self.playing = True
        self._timer.start(self.timer_interval)

    def pause(self) -> None:
        """Pausa a execução contínua."""
        self.playing = False
        self._timer.stop()

    def request_step(self, n: int = 1, reset_timer: bool = False) -> None:
        """Enfileira n passos e tenta disparar imediatamente.

        Args:
            n: Número de passos a enfileirar.
            reset_timer: Se True e em play, reinicia o timer para evitar
                disparo duplo após um comando manual.
        """
        self.pending_steps += n
        if reset_timer and self.playing:
            self._timer.stop()
            self._timer.start(self.timer_interval)
        self._try_emit()

    def set_timer_interval(self, ms: int) -> None:
        """Atualiza o intervalo do timer; reinicia se estiver em play.

        Args:
            ms: Novo intervalo em milissegundos.
        """
        self.timer_interval = ms
        if self.playing:
            self._timer.stop()
            self._timer.start(ms)

    def mark_step_started(self) -> None:
        """Registra que um passo foi iniciado (bloqueia novos disparos)."""
        self.step_in_progress = True

    def mark_step_done(self) -> None:
        """Registra que o passo atual terminou e tenta disparar o próximo."""
        self.step_in_progress = False
        self._try_emit()

    # Métodos internos

    def _on_tick(self) -> None:
        """Callback do timer: enfileira um passo a cada tick."""
        self.request_step(1)

    def _try_emit(self) -> None:
        """Emite step_requested se não há passo em andamento e há passos pendentes."""
        if self.step_in_progress or self.pending_steps <= 0:
            return
        self.pending_steps -= 1
        self.step_requested.emit()
