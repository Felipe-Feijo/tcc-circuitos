from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF
from simulation.nodes.relief_valve import DirectOperatedReliefValve as DirectOperatedReliefValveNode


from graphics.items.base.nodes.node_item import NodeItem
from graphics.utils.properties_dialog import PropertiesDialog
from ....anchors.anchor import AnchorItem


class DirectOperatedReliefValve(NodeItem):
    node_type = "direct_operated_relief_valve"
    simulation_cls = DirectOperatedReliefValveNode
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


        self.properties = {
            "p_set": 100
        }
        

        self.pixmap = QPixmap("resources/nodes/direct_operated_relief_valve/direct_operated_relief_valve.png")
        

        self.width = self.pixmap.width()
        self.height = self.pixmap.height()

        # Anchors do node
        self.add_anchor(AnchorItem("T", QPointF(self.width*99/199, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))
        self.add_anchor(AnchorItem("P", QPointF(self.width*99/199, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))

    def build_properties_dialog(self):
        dialog = PropertiesDialog(title="Relief Valve — Properties")
        if self.domain == "hydraulic":
            dialog._field_p_set = dialog.add_number_field("P set (Pa)", placeholder="ex: 0.85 ou 1.5e-3", value=self.properties.get("p_set"))
        else:
            dialog._field_p_set = None

        return dialog

    def apply_properties_from_dialog(self, dialog):
        if dialog._field_p_set is not None:
            p_set_text = dialog._field_p_set.text().strip()
            self.properties["p_set"] = float(p_set_text) if p_set_text else None