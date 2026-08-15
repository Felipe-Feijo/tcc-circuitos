"""Grava posição dos pistões e um snapshot visual do circuito a cada step."""

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

        self._frames: list[Frame] = []
        self._temp_dir = tempfile.mkdtemp(prefix="circuit_report_")
        self._step_index = 0
        self._finalized = False

        # Dimensões dos frames fixadas na criação: `scene.sceneRect()` pode
        # mudar durante a simulação (zoom/pan do usuário), e o encoder de
        # vídeo rejeita frames com dimensões inconsistentes.
        rect = self.scene.sceneRect()
        self._frame_width = max(1, int(rect.width()))
        self._frame_height = max(1, int(rect.height()))

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

    def set_dt(self, dt: float) -> None:
        """Atualiza o `dt` usado no cálculo de `sim_time` dos próximos
        frames capturados (ex: quando o usuário muda o dt em pleno run)."""
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
        """Cor de fundo do frame, espelhando o tema atual da cena.

        `scene.render()` bypassa a QGraphicsView (só ela tinha a cor do
        tema antes desta correção), então o preenchimento inicial do
        QImage precisa vir da própria cena — senão componentes desenhados
        para o tema escuro ficam invisíveis contra um fundo branco fixo.
        Cai para branco se a cena não tiver um `backgroundBrush` definido
        (ex: cena de teste isolada, sem passar por `set_light_theme`).
        """
        brush = self.scene.backgroundBrush()
        if brush.style() == Qt.BrushStyle.NoBrush:
            return Qt.GlobalColor.white
        return brush.color()
