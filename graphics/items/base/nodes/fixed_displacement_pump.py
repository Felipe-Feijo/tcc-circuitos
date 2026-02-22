from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF


from graphics.items.base.nodes.node_item import NodeItem
from graphics.utils.properties_dialog import PropertiesDialog
from ....anchors.anchor import AnchorItem


class FixedDisplacementPump(NodeItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.node_type = "fixed_displacement_pump"

        self.properties = {
            "Q": 1e-4  # default flow rate
        }
        

        self.pixmap = QPixmap("resources/nodes/fixed_displacement_pump/fixed_displacement_pump.png")
        

        self.width = self.pixmap.width()
        self.height = self.pixmap.height()

        # Anchors do node
        self.add_anchor(AnchorItem("S", QPointF(self.width*28/84, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom", "right", "left"]}))
        self.add_anchor(AnchorItem("P", QPointF(self.width*28/84, 0), node=self, domain=self.domain, exit_directions={"external": ["top", "right", "left"]}))

    def build_properties_dialog(self):
        dialog = PropertiesDialog(title="Fixed Displacement Pump — Properties")
        if self.domain == "hydraulic":
            dialog._field_Q = dialog.add_number_field("Q", placeholder="ex: 0.85 ou 1.5e-3", value=self.properties.get("Q"))
        else:
            dialog._field_Q = None

        return dialog

    def apply_properties_from_dialog(self, dialog):
        if dialog._field_Q is not None:
            Q_text = dialog._field_Q.text().strip()
            self.properties["Q"] = float(Q_text) if Q_text else None
