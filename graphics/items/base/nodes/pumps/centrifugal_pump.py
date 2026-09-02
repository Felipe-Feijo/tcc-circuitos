"""Graphics node for the centrifugal pump."""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QCoreApplication
from simulation.nodes.pumps.centrifugal_pump import CentrifugalPump as CentrifugalPumpNode

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.utils.properties_dialog import PropertiesDialog
from .....anchors.anchor import AnchorItem


class CentrifugalPump(NodeItem):
    node_type = "centrifugal_pump"
    simulation_cls = CentrifugalPumpNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("hydraulic",),
            sprite="resources/nodes/centrifugal_pump/centrifugal_pump.png",
            name=QCoreApplication.translate("CentrifugalPump", "Centrifugal Pump"),
        )

    def setup(self) -> None:
        self.properties = {}
        self.pixmap = QPixmap("resources/nodes/centrifugal_pump/centrifugal_pump.png")
        self.width  = self.pixmap.width()
        self.height = self.pixmap.height()

        self.add_anchor(AnchorItem("S", QPointF(self.width*28/84, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom", "right", "left"]}))
        self.add_anchor(AnchorItem("P", QPointF(self.width*28/84, 0), node=self, domain=self.domain, exit_directions={"external": ["top", "right", "left"]}))

    def build_properties_dialog(self):
        dialog = PropertiesDialog(title="Centrifugal Pump — Properties")
        if self.domain == "hydraulic":
            dialog._field_h = dialog.add_number_field(
                "Pressão de shutoff H (Pa)", placeholder="ex: 2e6",
                value=self.properties.get("H_shutoff"),
                required=True,
            )
            dialog._field_qmax = dialog.add_number_field(
                "Vazão máxima Q_max (m³/s)", placeholder="ex: 8.3e-4  (= 50 L/min)",
                value=self.properties.get("Q_max"),
                required=True,
            )
        else:
            dialog._field_h = None
            dialog._field_qmax = None
        return dialog

    def apply_properties_from_dialog(self, dialog):
        if dialog._field_h is not None:
            h_text = dialog._field_h.text().strip()
            self.properties["H_shutoff"] = float(h_text) if h_text else None
        if dialog._field_qmax is not None:
            q_text = dialog._field_qmax.text().strip()
            self.properties["Q_max"] = float(q_text) if q_text else None
