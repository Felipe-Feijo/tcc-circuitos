"""Gas-charged hydraulic accumulator graphics node (Boyle's law, bladder)."""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QCoreApplication

from simulation.nodes.accumulator import Accumulator as AccumulatorNode
from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.utils.properties_dialog import PropertiesDialog
from ....anchors.anchor import AnchorItem

_SPRITE_DIR = "resources/nodes/accumulator"

# Marker travel range, in the body's space (85x195px) -- the straight
# wall between the capsule's two arcs. See docs/superpowers/specs/
# 2026-07-19-accumulator-design.md for the pixel measurements.
#
# "Tank level" style visual reading: fluid enters from the bottom, so
# the marker rises (smaller y) as Vf grows -- Vf=0 sits at the bottom
# (empty, an intuitive "low tank" reading), Vf=V0 sits at the top (full).
_TRAVEL_Y_TOP    = 39   # Vf=V0 -- marker at the top of the straight wall (full)
_TRAVEL_Y_BOTTOM = 124  # Vf=0 -- marker at the bottom of the straight wall (empty)
_LEVEL_LINE_Y    = 18   # local y in accumulator_level.png where the reference line sits
_LEVEL_OFFSET_X  = 6    # centers the marker's 72px within the body's 85px


class Accumulator(NodeItem):
    node_type = "accumulator"
    simulation_cls = AccumulatorNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("hydraulic",),
            sprite=f"{_SPRITE_DIR}/accumulator.png",
            name=QCoreApplication.translate("Accumulator", "Accumulator"),
        )

    def setup(self) -> None:
        self.properties = {"V0": None, "P0": None}

        self._body_pixmap  = QPixmap(f"{_SPRITE_DIR}/accumulator_body.png")
        self._level_pixmap = QPixmap(f"{_SPRITE_DIR}/accumulator_level.png")

        self.width  = self._body_pixmap.width()
        self.height = self._body_pixmap.height()
        self._level = 0.0  # Vf/V0 -- mirrors the domain node's get_visual_state()

        self.add_anchor(AnchorItem(
            "P",
            QPointF(42, 194),
            node=self,
            domain=self.domain,
            exit_directions={"external": ["bottom"]},
        ))

    def apply_properties(self) -> None:
        pass  # V0/P0 are runtime-only properties, nothing to visually rebuild

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _level_marker_y(self) -> float:
        return (
            _TRAVEL_Y_BOTTOM
            - self._level * (_TRAVEL_Y_BOTTOM - _TRAVEL_Y_TOP)
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
    # Simulation
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
    # Properties
    # ------------------------------------------------------------------

    def build_properties_dialog(self) -> PropertiesDialog:
        dialog = PropertiesDialog(title=self.tr("Accumulator — Properties"))
        dialog._field_v0 = dialog.add_number_field(
            self.tr("Total volume V0 (m³)"),
            placeholder="ex: 0.001",
            value=self.properties.get("V0"),
            required=True,
        )
        dialog._field_p0 = dialog.add_number_field(
            self.tr("Precharge pressure P0 (Pa)"),
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
