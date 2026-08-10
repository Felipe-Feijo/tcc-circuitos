"""Nó gráfico de válvula de alívio de ação direta (sequence valve quando
pilotada — ver properties["piloted"])."""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF
from simulation.nodes.relief_valve import ReliefValve as ReliefValveNode

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.utils.properties_dialog import PropertiesDialog
from ....anchors.anchor import AnchorItem

_SPRITE_DIR = "resources/nodes/relief_valve"


class ReliefValve(NodeItem):
    node_type = "relief_valve"
    simulation_cls = ReliefValveNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("hydraulic",),
            sprite=f"{_SPRITE_DIR}/relief_valve.png",
            name="Relief Valve (direct)",
        )

    def setup(self) -> None:
        self.properties = {}
        self.pixmap = QPixmap(f"{_SPRITE_DIR}/relief_valve.png")
        self.width  = self.pixmap.width()
        self.height = self.pixmap.height()

        self.add_anchor(AnchorItem("T", QPointF(self.width*99/199, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))
        self.add_anchor(AnchorItem("P", QPointF(self.width*99/199, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))

    def build_properties_dialog(self):
        dialog = PropertiesDialog(title="Relief Valve — Properties")
        if self.domain == "hydraulic":
            dialog._field_p_set = dialog.add_number_field(
                "Pressão de abertura (Pa)", placeholder="ex: 1.5e7  (= 150 bar)",
                value=self.properties.get("p_set"),
                required=True,
            )
        else:
            dialog._field_p_set = None
        return dialog

    def apply_properties_from_dialog(self, dialog):
        if dialog._field_p_set is not None:
            p_set_text = dialog._field_p_set.text().strip()
            self.properties["p_set"] = float(p_set_text) if p_set_text else None