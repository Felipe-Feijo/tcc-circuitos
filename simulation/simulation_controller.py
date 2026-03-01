from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from simulation.simulation_engine import SimulationEngine
from collections import deque

class SimulationController(QObject):
    state_changed = pyqtSignal()
    def __init__(self, engine: SimulationEngine, max_history=5):
        super().__init__()

        self.engine = engine

        self.on_update_node = None      # dict[NodeItem, DomainNode]
        self.on_update_connection = None  # dict[ConnectionItem, Connection]

        # ───────── Controle de execução ─────────
        self.pending_steps = 0
        self.step_in_progress = False
        self.playing = False

        self.timer = QTimer()
        self.timer.timeout.connect(self._on_timer_tick)
        self.timer_interval = 1000  # Guarda o intervalo para poder resetar

        self.history = deque(maxlen=max_history)

    # ───────────── API pública (UI chama isso) ─────────────

    def play(self):
        if self.playing:
            return
        self.playing = True
        self.timer.start(self.timer_interval)

    def pause(self):
        self.playing = False
        self.timer.stop()

    def request_step(self, n: int = 1, reset_timer: bool = False):
        """
        Solicita n steps.
        
        Args:
            n: número de steps a executar
            reset_timer: se True e playing=True, reinicia o timer para evitar
                        steps muito próximos
        """
        self.pending_steps += n
        
        # 🔄 RESET DO TIMER se solicitado e em modo play
        if reset_timer and self.playing:
            self.timer.stop()
            self.timer.start(self.timer_interval)
        
        self._try_consume_steps()

    def command(self, node_id: str, cmd: str):
        node = self.engine.nodes.get(node_id)
        if not node:
            print(f"Node {node_id} not found")
            return

        node.handle_command(cmd)

        # ✅ Solicita step E reseta o timer
        self.request_step(1, reset_timer=True)

    # ───────────── Interno ─────────────

    def _on_timer_tick(self):
        self.request_step(1)

    def _try_consume_steps(self):
        if self.step_in_progress or self.pending_steps <= 0:
            return

        self._execute_step()

    def _execute_step(self):
        self.step_in_progress = True
        print("Executing simulation step...")
        self.pending_steps -= 1

        try:
            self.engine.run_until_stable()
            self._sync_view()

            # 📸 SEMPRE salva estado anterior
            self._push_snapshot()

        finally:
            print("Step complete.")
            self.step_in_progress = False
            self.state_changed.emit()

        self._try_consume_steps()

    def _sync_view(self):
        if self.on_update_node:
            for node_item, domain_node in self.on_update_node.items():
                node_item.update_from_domain(domain_node)

        if self.on_update_connection:
            for conn_item, domain_conn in self.on_update_connection.items():
                conn_item.set_state(domain_conn.get_state())

    # -----------------------
    # State snapshot helpers
    # -----------------------

    def _snapshot(self):
        return {
            node_id: node.get_state()
            for node_id, node in self.engine.nodes.items()
        }

    def _restore(self, snapshot):
        for node_id, state in snapshot.items():
            self.engine.nodes[node_id].set_state(state)

    def step_forward(self):
        if self.playing:
            return False

        self.request_step(1)
        return True

    def step_backward(self):
        if self.playing or not self.can_step_back():
            return False

        self.history.pop()
        self._restore(self.history[-1])

        # 🔹 reconstroi outputs derivados
        self.engine.compute_outputs(dt = 0)

        self._sync_view()
        self.state_changed.emit()
        return True
    
    def can_step_back(self):
        return len(self.history) > 1
    
    def _push_snapshot(self):
        snap = self._snapshot()

        if self.history and snap == self.history[-1]:
            return False

        self.history.append(snap)
        return True
    
    def set_timer_interval(self, ms: int):
        """Permite ajustar a velocidade do modo play"""
        self.timer_interval = ms
        if self.playing:
            self.timer.stop()
            self.timer.start(self.timer_interval)