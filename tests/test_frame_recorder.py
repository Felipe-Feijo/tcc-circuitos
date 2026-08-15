import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsRectItem
app = QApplication.instance() or QApplication([])

from simulation.nodes.cylinder.single_acting_cylinder import SingleActingCylinder
from simulation.simulation_engine import SimulationEngine
from simulation.report.frame_recorder import FrameRecorder


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
