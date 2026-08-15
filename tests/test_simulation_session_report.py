import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import shutil
import tempfile

import pytest
from PyQt6.QtWidgets import QApplication, QGraphicsScene
app = QApplication.instance() or QApplication([])

from simulation.nodes.cylinder.single_acting_cylinder import SingleActingCylinder
from simulation.graph_builder import GraphBuilder
import simulation.simulation_session as session_module
from simulation.simulation_session import SimulationSession, ReportResult


@pytest.fixture(autouse=True)
def _cleanup_report_temp_dirs():
    """Apaga todo diretório `circuit_report_*` criado (via FrameRecorder)
    durante o teste, esteja o relatório finalizado, descartado ou perdido
    por causa de uma falha simulada em `report_builder.build`."""
    created = []
    original_mkdtemp = tempfile.mkdtemp

    def tracking_mkdtemp(*args, **kwargs):
        path = original_mkdtemp(*args, **kwargs)
        created.append(path)
        return path

    tempfile.mkdtemp = tracking_mkdtemp
    try:
        yield
    finally:
        tempfile.mkdtemp = original_mkdtemp
        for path in created:
            shutil.rmtree(path, ignore_errors=True)


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
    assert os.path.exists(os.path.join(result.report_dir, "relatorio.html"))
    assert os.path.exists(os.path.join(result.report_dir, "graficos.pdf"))


def test_stop_returns_none_and_resets_state_when_build_raises(monkeypatch):
    """Uma falha de I/O em report_builder.build() não deve deixar a sessão
    travada em active=True para sempre."""
    _patch_build_graph(monkeypatch)
    scene = QGraphicsScene(0, 0, 100, 100)
    session = SimulationSession(scene)
    session.start()

    def boom(*args, **kwargs):
        raise OSError("disco cheio")

    monkeypatch.setattr(session_module.report_builder, "build", boom)

    result = session.stop()

    assert result is None
    assert session.active is False
    assert session.engine is None
    assert session.controller is None

    # a sessão deve poder ser reiniciada normalmente depois da falha
    error = session.start()
    assert error is None
    assert session.active is True
