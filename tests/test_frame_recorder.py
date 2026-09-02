import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import shutil
import tempfile

import pytest
from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsRectItem
app = QApplication.instance() or QApplication([])

from simulation.nodes.cylinder.single_acting_cylinder import SingleActingCylinder
from simulation.simulation_engine import SimulationEngine
from simulation.report.frame_recorder import FrameRecorder


@pytest.fixture(autouse=True)
def _cleanup_report_temp_dirs():
    """Apaga todo diretório `circuit_report_*` criado por um FrameRecorder
    durante o teste, mesmo que o teste não chame `.discard()`."""
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


def _build_engine_with_piston():
    """Cilindro digital (domain=None) — sem exigir bore/stroke/spring_k."""
    cyl = SingleActingCylinder("c1", domain=None)
    engine = SimulationEngine(nodes={"c1": cyl}, connections={})
    return engine, cyl


def _build_scene():
    scene = QGraphicsScene(0, 0, 200, 100)
    scene.addItem(QGraphicsRectItem(10, 10, 50, 50))
    return scene


def test_capture_step_records_piston_position():
    engine, cyl = _build_engine_with_piston()
    scene = _build_scene()
    recorder = FrameRecorder(engine, scene, dt=0.1)

    cyl.position = 0
    recorder.capture_step()
    cyl.position = 1
    recorder.capture_step()

    data = recorder.finalize()
    assert [f.piston_positions["c1"] for f in data.frames] == [0, 1]


def test_capture_step_sets_step_index_and_sim_time():
    engine, cyl = _build_engine_with_piston()
    scene = _build_scene()
    recorder = FrameRecorder(engine, scene, dt=0.25)

    recorder.capture_step()
    recorder.capture_step()

    data = recorder.finalize()
    assert [f.step_index for f in data.frames] == [0, 1]
    assert [f.sim_time for f in data.frames] == [0.0, 0.25]


def test_capture_step_writes_png_file():
    engine, cyl = _build_engine_with_piston()
    scene = _build_scene()
    recorder = FrameRecorder(engine, scene, dt=0.1)

    recorder.capture_step()
    data = recorder.finalize()

    assert len(data.frames) == 1
    image_path = data.frames[0].image_path
    assert os.path.exists(image_path)
    assert os.path.getsize(image_path) > 0


def test_ignores_non_piston_nodes():
    from simulation.nodes.nodes import Node

    class FakeValve(Node):
        def get_visual_state(self):
            return "open"

    valve = FakeValve("v1", "valve_4_2_ways", domain=None)
    engine, cyl = _build_engine_with_piston()
    engine.nodes["v1"] = valve
    scene = _build_scene()
    recorder = FrameRecorder(engine, scene, dt=0.1)

    recorder.capture_step()
    data = recorder.finalize()

    assert list(data.frames[0].piston_positions.keys()) == ["c1"]


def test_finalize_stops_accepting_frames():
    engine, cyl = _build_engine_with_piston()
    scene = _build_scene()
    recorder = FrameRecorder(engine, scene, dt=0.1)

    recorder.capture_step()
    recorder.finalize()
    recorder.capture_step()  # não deve ser aceito após finalize()

    data2 = recorder.finalize()
    assert len(data2.frames) == 1


def test_frame_dimensions_stay_fixed_across_scene_rect_changes():
    """Zoom/pan mid-simulação muda `scene.sceneRect()` — as dimensões dos
    PNGs gravados devem permanecer as mesmas (fixadas na criação do
    recorder), senão o encoder de vídeo rejeita o frame com shape diferente."""
    from PyQt6.QtGui import QImage

    engine, cyl = _build_engine_with_piston()
    scene = _build_scene()
    recorder = FrameRecorder(engine, scene, dt=0.1)

    recorder.capture_step()
    scene.setSceneRect(0, 0, 800, 600)  # simula zoom/pan
    recorder.capture_step()

    data = recorder.finalize()
    assert len(data.frames) == 2

    sizes = [QImage(f.image_path).size() for f in data.frames]
    assert sizes[0] == sizes[1]

    recorder.discard()


def test_frame_background_matches_scene_theme():
    """A cena carrega o tema atual via `setBackgroundBrush` (espelhado pelo
    MainWindow.set_light_theme); o frame renderizado deve usar essa cor,
    não branco fixo, senão componentes desenhados para tema escuro somem."""
    from PyQt6.QtGui import QBrush, QColor, QImage

    engine, cyl = _build_engine_with_piston()
    scene = _build_scene()
    dark = QColor(30, 30, 30)
    scene.setBackgroundBrush(QBrush(dark))
    recorder = FrameRecorder(engine, scene, dt=0.1)

    recorder.capture_step()
    data = recorder.finalize()

    image = QImage(data.frames[0].image_path)
    corner_pixel = QColor(image.pixel(0, 0))
    assert (corner_pixel.red(), corner_pixel.green(), corner_pixel.blue()) == (30, 30, 30)

    recorder.discard()


def test_frame_background_falls_back_to_white_without_scene_brush():
    """Cena sem `backgroundBrush` definido (ex: cena de teste isolada) não
    deve quebrar — cai para o branco de sempre."""
    from PyQt6.QtGui import QColor, QImage

    engine, cyl = _build_engine_with_piston()
    scene = _build_scene()  # sem setBackgroundBrush
    recorder = FrameRecorder(engine, scene, dt=0.1)

    recorder.capture_step()
    data = recorder.finalize()

    image = QImage(data.frames[0].image_path)
    corner_pixel = QColor(image.pixel(0, 0))
    assert (corner_pixel.red(), corner_pixel.green(), corner_pixel.blue()) == (255, 255, 255)

    recorder.discard()


def _add_gauge(engine, domain, node_id="g1"):
    from simulation.nodes.pressure_gauge import PressureGauge

    gauge = PressureGauge(node_id, domain=domain)
    gauge.add_anchor("P", domain=domain)
    engine.nodes[node_id] = gauge
    return gauge


def test_capture_step_records_hydraulic_gauge_pressure():
    engine, cyl = _build_engine_with_piston()
    gauge = _add_gauge(engine, "hydraulic")
    gauge.anchors["P"].pressure = 5e6
    scene = _build_scene()
    recorder = FrameRecorder(engine, scene, dt=0.1)

    recorder.capture_step()

    data = recorder.finalize()
    assert data.frames[0].gauge_readings["g1"] == pytest.approx(5e6)


def test_capture_step_records_pneumatic_gauge_state():
    engine, cyl = _build_engine_with_piston()
    gauge = _add_gauge(engine, "pneumatic")
    gauge.anchors["P"].state = True
    scene = _build_scene()
    recorder = FrameRecorder(engine, scene, dt=0.1)

    recorder.capture_step()

    data = recorder.finalize()
    assert data.frames[0].gauge_readings["g1"] is True


def test_gauge_readings_ignores_non_gauge_nodes():
    engine, cyl = _build_engine_with_piston()
    scene = _build_scene()
    recorder = FrameRecorder(engine, scene, dt=0.1)

    recorder.capture_step()

    data = recorder.finalize()
    assert data.frames[0].gauge_readings == {}


def test_capture_step_skips_rendering_when_video_disabled():
    engine, cyl = _build_engine_with_piston()
    scene = _build_scene()
    recorder = FrameRecorder(engine, scene, dt=0.1, capture_video=False)

    cyl.position = 0.5
    recorder.capture_step()

    data = recorder.finalize()
    assert len(data.frames) == 1
    assert data.frames[0].image_path == ""
    assert data.frames[0].piston_positions == {"c1": 0.5}


def test_set_dt_changes_subsequent_sim_time():
    engine, cyl = _build_engine_with_piston()
    scene = _build_scene()
    recorder = FrameRecorder(engine, scene, dt=0.1)

    recorder.capture_step()  # sim_time = 0.0
    recorder.set_dt(1.0)
    recorder.capture_step()  # sim_time = 1 * 1.0 = 1.0

    data = recorder.finalize()
    assert [f.sim_time for f in data.frames] == [0.0, 1.0]

    recorder.discard()
