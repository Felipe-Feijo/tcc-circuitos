from PyQt6.QtCore import QPointF
from graphics.anchors.anchor import AnchorItem
from graphics.items.base.nodes.cylinder.cylinder_item import CylinderItem

class SingleActingCylinder(CylinderItem):

    BODY_VISUALS = {
        0: {
            "sprite": "resources/nodes/single_acting_cylinder/single_acting_cylinder_retracted.png",
            "offset": QPointF(0, 0),
        },
        1: {
            "sprite": "resources/nodes/single_acting_cylinder/single_acting_cylinder_extended.png",
            "offset": QPointF(0, 0),
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.node_type = "single_acting_cylinder"

        if self.domain == "hydraulic":
            self.properties.setdefault("bore", 0.05)
            self.properties.setdefault("stroke", 0.1)
            self.properties.setdefault("spring_k", 0.0)
            self.properties.setdefault("external_force", 0.0)
            self.properties.setdefault("friction", 0.0)

    def initialize_anchors(self):
        self.add_anchor(AnchorItem("A", QPointF(self.width * 18/360, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))

    def build_properties_dialog(self):
        dialog = super().build_properties_dialog()

        if self.domain == "hydraulic":
            dialog._field_bore         = dialog.add_number_field("Diâmetro do furo (m)", placeholder="ex: 0.05", value=self.properties.get("bore"))
            dialog._field_stroke       = dialog.add_number_field("Curso (m)", placeholder="ex: 0.1", value=self.properties.get("stroke"))
            dialog._field_spring_k = dialog.add_number_field("Constante elástica da mola (N/m)", placeholder="ex: 10.0", value=self.properties.get("spring_k"))
            dialog._field_ext_force    = dialog.add_number_field("Carga externa (N)", placeholder="ex: 0.0", value=self.properties.get("external_force"))
            dialog._field_friction     = dialog.add_number_field("Fricção (N·s/m)", placeholder="ex: 0.0", value=self.properties.get("friction"))
        else:
            dialog._field_bore = dialog._field_stroke = None
            dialog._field_spring_k = dialog._field_ext_force = dialog._field_friction = None

        return dialog

    def apply_properties_from_dialog(self, dialog):
        super().apply_properties_from_dialog(dialog)

        if dialog._field_bore is not None:
            for field, key in [
                (dialog._field_bore,         "bore"),
                (dialog._field_stroke,       "stroke"),
                (dialog._field_spring_k, "spring_k"),
                (dialog._field_ext_force,    "external_force"),
                (dialog._field_friction,     "friction"),
            ]:
                text = field.text().strip()
                self.properties[key] = float(text) if text else None