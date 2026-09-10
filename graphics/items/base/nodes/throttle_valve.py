"""Graphics node for the throttle valve (hydraulic only, fixed orifice).

Sprite layout
-------------
Single static sprite -- no visual state, the restriction is fixed
(unlike CheckValve/ThrottleCheckValve, which latch open/closed).

Anchor X (left) : (0, height/2)      exit -> left
Anchor Y (right): (width, height/2)  exit -> right
"""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QCoreApplication

from simulation.nodes.throttle_valve import ThrottleValve as ThrottleValveNode
from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.utils.properties_dialog import PropertiesDialog
from ....anchors.anchor import AnchorItem

_SPRITE_DIR = "resources/nodes/throttle_valve"


class ThrottleValve(NodeItem):
    node_type = "throttle_valve"
    simulation_cls = ThrottleValveNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("hydraulic",),
            sprite=f"{_SPRITE_DIR}/throttle_valve.png",
            name=QCoreApplication.translate("ThrottleValve", "Throttle Valve"),
        )

    def setup(self) -> None:
        self.properties = {}

        self.pixmap = QPixmap(f"{_SPRITE_DIR}/throttle_valve.png")
        self.width  = self.pixmap.width()
        self.height = self.pixmap.height()

        self.add_anchor(AnchorItem(
            "X", QPointF(0, self.height / 2), node=self, domain=self.domain,
            exit_directions={"external": ["left"]},
        ))
        self.add_anchor(AnchorItem(
            "Y", QPointF(self.width, self.height / 2), node=self, domain=self.domain,
            exit_directions={"external": ["right"]},
        ))

    # ------------------------------------------------------------------
    # Properties dialog
    # ------------------------------------------------------------------

    def build_properties_dialog(self) -> PropertiesDialog:
        dialog = PropertiesDialog(title=self.tr("Throttle Valve — Properties"))
        dialog._field_k = dialog.add_number_field(
            self.tr("Conductance k (m³/s/√Pa)"),
            placeholder="ex: 1.5e-8",
            value=self.properties.get("k"),
            required=True,
        )
        return dialog

    def apply_properties_from_dialog(self, dialog: PropertiesDialog) -> None:
        k_text = dialog._field_k.text().strip()
        self.properties["k"] = float(k_text) if k_text else None
