import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from PyQt6.QtWidgets import QApplication, QGraphicsScene
app = QApplication.instance() or QApplication([])

from simulation.nodes.cylinder.single_acting_cylinder import SingleActingCylinder
from simulation.graph_builder import GraphBuilder
import simulation.simulation_session as session_module
from simulation.simulation_session import SimulationSession, ReportResult


def _patch_build_graph(monkeypatch):
    """Substitui EditorController.build_graph por um grafo fixo com um
    único pistão digital, sem precisar montar itens gráficos reais na cena
    (a cena só é usada pelo FrameRecorder para renderizar o PNG do frame,
    o que funciona igual esteja ela vazia ou não)."""
    def fake_build_graph(self):
        builder = GraphBuilder()
        builder.nodes["c1"] = SingleActingCylinder("c1", domain=None)
        return builder

    monkeypatch.setattr(session_module.EditorController, "build_graph", fake_build_graph)


def test_stop_returns_none_when_never_started():
    scene = QGraphicsScene(0, 0, 100, 100)
    session = SimulationSession(scene)

    assert session.stop() is None


def test_stop_builds_report_and_returns_result(monkeypatch):
    _patch_build_graph(monkeypatch)
    scene = QGraphicsScene(0, 0, 100, 100)
    session = SimulationSession(scene)
    error = session.start()
    assert error is None

    session.controller.request_step(2)

    result = session.stop()

    assert result is not None
    assert isinstance(result, ReportResult)
    assert result.keep is False
    assert os.path.exists(os.path.join(result.report_dir, "relatorio.html"))
    assert os.path.exists(os.path.join(result.report_dir, "graficos.pdf"))


def test_mark_keep_report_sets_flag_on_result(monkeypatch):
    _patch_build_graph(monkeypatch)
    scene = QGraphicsScene(0, 0, 100, 100)
    session = SimulationSession(scene)
    session.start()

    session.mark_keep_report()
    result = session.stop()

    assert result.keep is True


def test_mark_keep_report_before_start_is_a_noop():
    scene = QGraphicsScene(0, 0, 100, 100)
    session = SimulationSession(scene)

    session.mark_keep_report()  # não deve lançar exceção
