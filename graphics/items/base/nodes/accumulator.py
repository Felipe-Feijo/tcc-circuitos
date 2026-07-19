"""Nó gráfico de acumulador hidráulico a gás (lei de Boyle, bexiga)."""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF

from simulation.nodes.accumulator import Accumulator as AccumulatorNode
from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.utils.properties_dialog import PropertiesDialog
from ....anchors.anchor import AnchorItem

_SPRITE_DIR = "resources/nodes/accumulator"

# Faixa de curso do marcador, no espaço do body (85x195px) -- parede reta
# entre os dois arcos da cápsula. Ver docs/superpowers/specs/
# 2026-07-19-accumulator-design.md para o levantamento de pixels.
_TRAVEL_Y_TOP    = 39   # Vf=0 -- marcador no topo da parede reta (vazio)
_TRAVEL_Y_BOTTOM = 124  # Vf=V0 -- marcador no fundo da parede reta (cheio)
_LEVEL_LINE_Y    = 18   # y local em accumulator_level.png onde fica a linha de referência
_LEVEL_OFFSET_X  = 6    # centraliza os 72px do marcador nos 85px do body


class Accumulator(NodeItem):
    node_type = "accumulator"
    simulation_cls = AccumulatorNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("hydraulic",),
            sprite=f"{_SPRITE_DIR}/accumulator_body.png",
            name="Accumulator",
        )

    def setup(self) -> None:
        self.properties = {"V0": None, "P0": None}

        self._body_pixmap  = QPixmap(f"{_SPRITE_DIR}/accumulator_body.png")
        self._level_pixmap = QPixmap(f"{_SPRITE_DIR}/accumulator_level.png")

        self.width  = self._body_pixmap.width()
        self.height = self._body_pixmap.height()
        self._level = 0.0  # Vf/V0 -- espelha get_visual_state() do nó de domínio

        self.add_anchor(AnchorItem(
            "P",
            QPointF(42, 194),
            node=self,
            domain=self.domain,
            exit_directions={"external": ["bottom"]},
        ))

    def apply_properties(self) -> None:
        pass  # V0/P0 são propriedades runtime-only, nada pra reconstruir visualmente

    # ------------------------------------------------------------------
    # Desenho
    # ------------------------------------------------------------------

    def _level_marker_y(self) -> float:
        return (
            _TRAVEL_Y_TOP
            + self._level * (_TRAVEL_Y_BOTTOM - _TRAVEL_Y_TOP)
            - _LEVEL_LINE_Y
        )

    def paint(self, painter, option, widget=None) -> None:
        painter.save()
        self.draw_pixmap(painter, QPointF(0, 0), self._body_pixmap)
        self.draw_pixmap(
            painter,
            QPointF(_LEVEL_OFFSET_X, self._level_marker_y()),
            self._level_pixmap,
        )
        self.paint_selection_feedback(painter)
        painter.restore()

    # ------------------------------------------------------------------
    # Simulação
    # ------------------------------------------------------------------

    def update_from_domain(self, domain_node) -> None:
        super().update_from_domain(domain_node)
        self._level = domain_node.get_visual_state()
        self.update()

    def reset_visual_state(self) -> None:
        super().reset_visual_state()
        self._level = 0.0
        self.update()

    # ------------------------------------------------------------------
    # Propriedades
    # ------------------------------------------------------------------

    def build_properties_dialog(self) -> PropertiesDialog:
        dialog = PropertiesDialog(title="Accumulator — Properties")
        dialog._field_v0 = dialog.add_number_field(
            "Volume total V0 (m³)",
            placeholder="ex: 0.001",
            value=self.properties.get("V0"),
            required=True,
        )
        dialog._field_p0 = dialog.add_number_field(
            "Pressão de pré-carga P0 (Pa)",
            placeholder="ex: 3e6",
            value=self.properties.get("P0"),
            required=True,
        )
        return dialog

    def apply_properties_from_dialog(self, dialog: PropertiesDialog) -> None:
        v0_text = dialog._field_v0.text().strip()
        p0_text = dialog._field_p0.text().strip()
        self.properties["V0"] = float(v0_text) if v0_text else None
        self.properties["P0"] = float(p0_text) if p0_text else None
