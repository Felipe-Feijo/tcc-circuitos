"""Graphics node for the single-stage, direct-acting pressure reducing valve.

Sprite layout
-------------
Width x Height: 200 x 162 px
Anchor P (top)  : (width*98.5/200, 0)          inlet  -> top
Anchor A (base) : (width*98.5/200, height)     outlet -> bottom
Anchor T (base) : (width*134.5/200, height)    relief -> bottom
                  present only when properties["relieving"] is True.
                  Measured from pressure_reducing_valve_relief.png's
                  opaque pixels: the line reaches the bottom edge at
                  x=132..137, center 134.5.

Sprites
-------
pressure_reducing_valve.png        -- body (ISO schematic, single stage).
pressure_reducing_valve_relief.png -- tank/relief port overlay (T port
                                       line), drawn on top of the body
                                       when relieving=True.
"""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QCoreApplication
from simulation.nodes.pressure_reducing_valve import PressureReducingValve as PressureReducingValveNode

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.utils.properties_dialog import PropertiesDialog
from ....anchors.anchor import AnchorItem

_SPRITE_DIR = "resources/nodes/pressure_reducing_valve"


class PressureReducingValve(NodeItem):
    node_type = "pressure_reducing_valve"
    simulation_cls = PressureReducingValveNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("hydraulic",),
            sprite=f"{_SPRITE_DIR}/pressure_reducing_valve.png",
            name=QCoreApplication.translate("PressureReducingValve", "Pressure Reducing Valve"),
        )

    def setup(self) -> None:
        self.properties = {"relieving": False}
        self.pixmap = QPixmap(f"{_SPRITE_DIR}/pressure_reducing_valve.png")
        self.width  = self.pixmap.width()
        self.height = self.pixmap.height()

        self.add_anchor(AnchorItem("P", QPointF(self.width*98.5/200, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))
        self.add_anchor(AnchorItem("A", QPointF(self.width*98.5/200, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))

        self._pixmap_relief = QPixmap(f"{_SPRITE_DIR}/pressure_reducing_valve_relief.png")
        self._relief_overlay = None
        self._update_relief_anchor()

    def _update_relief_anchor(self) -> None:
        """Adds/removes the T anchor and the relief overlay based on
        self.properties. Called in setup() and whenever the property
        changes (apply_properties / apply_properties_from_dialog)."""
        if self.properties.get("relieving"):
            self.add_anchor(AnchorItem(
                "T", QPointF(self.width*134.5/200, self.height), node=self, domain=self.domain,
                exit_directions={"external": ["bottom"]},
            ))
            self._relief_overlay = self._pixmap_relief
        else:
            self.remove_anchor("T")
            self._relief_overlay = None

    def apply_properties(self) -> None:
        self._update_relief_anchor()
        self.update()

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self._relief_overlay is not None:
            painter.save()
            painter.translate(self._visual_offset)
            self.draw_pixmap(painter, QPointF(0, 0), self._relief_overlay)
            painter.restore()

    def build_properties_dialog(self):
        dialog = PropertiesDialog(title=self.tr("Pressure Reducing Valve — Properties"))
        dialog._field_p_set = dialog.add_number_field(
            self.tr("Setpoint pressure (Pa)"), placeholder="ex: 1.5e7  (= 150 bar)",
            value=self.properties.get("p_set"),
            required=True,
        )
        dialog._field_relieving = dialog.add_bool_field(
            self.tr("Tank port (T)"), value=self.properties.get("relieving", False),
        )
        return dialog

    def apply_properties_from_dialog(self, dialog):
        p_set_text = dialog._field_p_set.text().strip()
        self.properties["p_set"] = float(p_set_text) if p_set_text else None
        self.properties["relieving"] = dialog._field_relieving.isChecked()
        self._update_relief_anchor()
        self.update()
