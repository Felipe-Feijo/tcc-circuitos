"""Records piston positions and a visual snapshot of the circuit at each step."""

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QImage, QPainter

logger = logging.getLogger(__name__)

PISTON_TYPES = ("single_acting_cylinder", "double_acting_cylinder")


@dataclass
class Frame:
    """One recorded instant of the simulation."""
    step_index: int
    sim_time: float
    piston_positions: dict
    image_path: str


@dataclass
class ReportData:
    """Data collected by a `FrameRecorder`, ready for `report_builder`."""
    frames: list = field(default_factory=list)
    temp_dir: str = ""


class FrameRecorder:
    """Records a simulation session's history to build a report.

    A `FrameRecorder` lives for the duration of an active simulation
    session: created in `SimulationSession.start()`, fed on each
    `SimulationController.state_changed` via `capture_step()`, and
    closed in `SimulationSession.stop()` via `finalize()`.

    Args:
        engine: The active session's `SimulationEngine` (source of `.nodes`).
        scene: The scene's `QGraphicsScene`, used to render each frame.
        dt: Simulated time interval between steps, used to compute each
            frame's `sim_time`.
    """

    def __init__(self, engine, scene, dt: float):
        self.engine = engine
        self.scene = scene
        self.dt = dt

        self._frames: list[Frame] = []
        self._temp_dir = tempfile.mkdtemp(prefix="circuit_report_")
        self._step_index = 0
        self._finalized = False

        # Frame dimensions fixed at creation: `scene.sceneRect()` can
        # change during simulation (user zoom/pan), and the video
        # encoder rejects frames with inconsistent dimensions.
        rect = self.scene.sceneRect()
        self._frame_width = max(1, int(rect.width()))
        self._frame_height = max(1, int(rect.height()))

    def capture_step(self) -> None:
        """Records a frame with the pistons' current position and a PNG of the scene.

        Does nothing if already finalized. A failure rendering the
        image is logged and the frame is skipped -- it never crashes
        the simulation.
        """
        if self._finalized:
            return

        positions = {
            node_id: node.get_visual_state()
            for node_id, node in self.engine.nodes.items()
            if getattr(node, "type", None) in PISTON_TYPES
        }

        image_path = os.path.join(self._temp_dir, f"frame_{self._step_index:05d}.png")
        try:
            self._render_frame(image_path)
        except Exception:
            logger.exception("failed to capture report frame %d", self._step_index)
            return

        self._frames.append(Frame(
            step_index=self._step_index,
            sim_time=self._step_index * self.dt,
            piston_positions=positions,
            image_path=image_path,
        ))
        self._step_index += 1

    def finalize(self) -> ReportData:
        """Ends the recording and returns the collected frames.

        Subsequent calls to `capture_step()` are ignored.
        """
        self._finalized = True
        return ReportData(frames=list(self._frames), temp_dir=self._temp_dir)

    def discard(self) -> None:
        """Deletes the temp directory holding every recorded frame."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def set_dt(self, dt: float) -> None:
        """Updates the `dt` used to compute `sim_time` for the next
        captured frames (e.g. when the user changes dt mid-run)."""
        self.dt = dt

    def _render_frame(self, path: str) -> None:
        image = QImage(self._frame_width, self._frame_height, QImage.Format.Format_ARGB32)
        image.fill(self._background_color())

        painter = QPainter(image)
        try:
            self.scene.render(painter, target=QRectF(image.rect()), source=self.scene.sceneRect())
        finally:
            painter.end()

        image.save(path)

    def _background_color(self):
        """The frame's background color, mirroring the scene's current theme.

        `scene.render()` bypasses QGraphicsView (only it had the theme
        color before this fix), so the QImage's initial fill needs to
        come from the scene itself -- otherwise components drawn for
        the dark theme become invisible against a fixed white
        background. Falls back to white if the scene has no
        `backgroundBrush` set (e.g. an isolated test scene, never
        passed through `set_light_theme`).
        """
        brush = self.scene.backgroundBrush()
        if brush.style() == Qt.BrushStyle.NoBrush:
            return Qt.GlobalColor.white
        return brush.color()
