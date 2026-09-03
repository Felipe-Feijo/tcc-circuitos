"""Graphics node for the single-stage, direct-acting pressure reducing valve.

Sprite layout
-------------
Width x Height: 200 x 162 px
Anchor P (top)  : (width*98.5/200, 0)        inlet  -> top
Anchor A (base) : (width*98.5/200, height)   outlet -> bottom

Single static sprite -- unlike ReliefValve there is no pilot overlay
and no dynamic visual state (only one PNG exists for this component,
matching what ReliefValve itself does despite also having two physical
regimes: no get_visual_state() override).

Sprites
-------
pressure_reducing_valve.png -- body (ISO schematic, single stage).
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
        self.properties = {}
        self.pixmap = QPixmap(f"{_SPRITE_DIR}/pressure_reducing_valve.png")
        self.width  = self.pixmap.width()
        self.height = self.pixmap.height()

        self.add_anchor(AnchorItem("P", QPointF(self.width*98.5/200, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))
        self.add_anchor(AnchorItem("A", QPointF(self.width*98.5/200, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))

    def apply_properties(self) -> None:
        self.update()

    def build_properties_dialog(self):
        dialog = PropertiesDialog(title=self.tr("Pressure Reducing Valve — Properties"))
        dialog._field_p_set = dialog.add_number_field(
            self.tr("Setpoint pressure (Pa)"), placeholder="ex: 1.5e7  (= 150 bar)",
            value=self.properties.get("p_set"),
            required=True,
        )
        return dialog

    def apply_properties_from_dialog(self, dialog):
        p_set_text = dialog._field_p_set.text().strip()
        self.properties["p_set"] = float(p_set_text) if p_set_text else None
        self.update()
