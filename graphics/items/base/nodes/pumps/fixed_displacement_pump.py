"""Graphics node for the fixed-displacement pump."""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QCoreApplication
from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump as FixedDisplacementPumpNode

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.utils.properties_dialog import PropertiesDialog
from .....anchors.anchor import AnchorItem


class FixedDisplacementPump(NodeItem):
    node_type = "fixed_displacement_pump"
    simulation_cls = FixedDisplacementPumpNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("hydraulic",),
            sprite="resources/nodes/fixed_displacement_pump/fixed_displacement_pump.png",
            name=QCoreApplication.translate("FixedDisplacementPump", "Fixed Displacement Pump"),
        )
    def setup(self) -> None:
        self.properties = {}
        self.pixmap = QPixmap("resources/nodes/fixed_displacement_pump/fixed_displacement_pump.png")
        self.width  = self.pixmap.width()
        self.height = self.pixmap.height()

        self.add_anchor(AnchorItem("S", QPointF(self.width*28/84, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom", "right", "left"]}))
        self.add_anchor(AnchorItem("P", QPointF(self.width*28/84, 0), node=self, domain=self.domain, exit_directions={"external": ["top", "right", "left"]}))

    def build_properties_dialog(self):
        dialog = PropertiesDialog(title="Fixed Displacement Pump — Properties")
        if self.domain == "hydraulic":
            dialog._field_Q = dialog.add_number_field(
                "Vazão (m³/s)", placeholder="ex: 8.3e-4  (= 50 L/min)",
                value=self.properties.get("Q"),
                required=True,
            )
        else:
            dialog._field_Q = None
        return dialog

    def apply_properties_from_dialog(self, dialog):
        if dialog._field_Q is not None:
            Q_text = dialog._field_Q.text().strip()
            self.properties["Q"] = float(Q_text) if Q_text else None
