"""Grava posição dos pistões e um snapshot visual do circuito a cada step."""

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter

logger = logging.getLogger(__name__)

PISTON_TYPES = ("single_acting_cylinder", "double_acting_cylinder")


@dataclass
class Frame:
    """Um instante gravado da simulação."""
    step_index: int
    sim_time: float
    piston_positions: dict
    image_path: str


@dataclass
class ReportData:
    """Dados coletados por um `FrameRecorder`, prontos para `report_builder`."""
    frames: list = field(default_factory=list)
    temp_dir: str = ""


class FrameRecorder:
    """Grava o histórico de uma sessão de simulação para gerar um relatório.

    Um `FrameRecorder` vive durante uma sessão de simulação ativa: é criado
    em `SimulationSession.start()`, alimentado a cada
    `SimulationController.state_changed` via `capture_step()`, e encerrado
    em `SimulationSession.stop()` via `finalize()`.

    Args:
        engine: `SimulationEngine` da sessão ativa (fonte de `.nodes`).
        scene: `QGraphicsScene` da cena, usada para renderizar cada frame.
        dt: Intervalo de tempo simulado entre steps, usado para calcular
            `sim_time` de cada frame.
    """

    def __init__(self, engine, scene, dt: float):
        self.engine = engine
        self.scene = scene
        self.dt = dt
        self.keep: bool = False

        self._frames: list[Frame] = []
        self._temp_dir = tempfile.mkdtemp(prefix="circuit_report_")
        self._step_index = 0
        self._finalized = False

    def capture_step(self) -> None:
        """Grava um frame com a posição atual dos pistões e um PNG da cena.

        Não faz nada se já foi finalizado. Falha ao renderizar a imagem é
        logada e pula o frame — nunca derruba a simulação.
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
            logger.exception("falha ao capturar frame %d do relatório", self._step_index)
            return

        self._frames.append(Frame(
            step_index=self._step_index,
            sim_time=self._step_index * self.dt,
            piston_positions=positions,
            image_path=image_path,
        ))
        self._step_index += 1

    def finalize(self) -> ReportData:
        """Encerra a gravação e devolve os frames coletados.

        Chamadas subsequentes a `capture_step()` são ignoradas.
        """
        self._finalized = True
        return ReportData(frames=list(self._frames), temp_dir=self._temp_dir)

    def discard(self) -> None:
        """Apaga o diretório temporário com todos os frames gravados."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _render_frame(self, path: str) -> None:
        rect = self.scene.sceneRect()
        width = max(1, int(rect.width()))
        height = max(1, int(rect.height()))

        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)

        painter = QPainter(image)
        try:
            self.scene.render(painter)
        finally:
            painter.end()

        image.save(path)
