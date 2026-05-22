"""Nó gráfico de cilindro de dupla ação."""

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPixmap
from graphics.anchors.anchor import AnchorItem
from graphics.items.base.nodes.cylinder.cylinder_item import CylinderItem
from simulation.nodes.cylinder.double_acting_cylinder import DoubleActingCylinder as DoubleActingCylinderNode

_BASE_PATH = "resources/nodes/double_acting_cylinder"

# Posições X da haste no espaço do body (em pixels)
_ROD_X_RETRACTED = 28
_ROD_X_EXTENDED  = 284
_ROD_DELTA       = _ROD_X_EXTENDED - _ROD_X_RETRACTED  # 256px

# Offsets relativos ao (0, 0) do body — ajustar após verificar sprites
_ROD_OFFSET = QPointF(0, 0)


class DoubleActingCylinder(CylinderItem):
    node_type = "double_acting_cylinder"
    simulation_cls = DoubleActingCylinderNode

    BODY_VISUALS = {
        0: {
            "sprite": f"{_BASE_PATH}/double_acting_cylinder_retracted.png",
            "offset": QPointF(0, 0),
        },
        1: {
            "sprite": f"{_BASE_PATH}/double_acting_cylinder_extended.png",
            "offset": QPointF(0, 0),
        }
    }

    def setup(self) -> None:
        super().setup()
        if self.domain == "hydraulic":
            # friction não aparece no dialog — fixo em 0 no nó de simulação
            self.properties.setdefault("external_force", 0.0)
            self._rod_pixmap  = QPixmap(f"{_BASE_PATH}/double_acting_cylinder_rod.png")
            self._body_pixmap = QPixmap(f"{_BASE_PATH}/double_acting_cylinder_body.png")

    def initialize_anchors(self):
        self.add_anchor(AnchorItem(
            "A",
            QPointF(self.width*18/497, self.height),
            node=self,
            domain=self.domain,
            exit_directions={"external": ["bottom"]}
        ))
        self.add_anchor(AnchorItem(
            "B",
            QPointF(self.width*408/497, self.height),
            node=self,
            domain=self.domain,
            exit_directions={"external": ["bottom"]}
        ))

    # ── pintura ───────────────────────────────────────────────────────────────

    def update_body_visuals(self):
        if self.domain != "hydraulic":
            super().update_body_visuals()

    def paint_body(self, painter):
        if self.domain != "hydraulic":
            super().paint_body(painter)
            return

        t  = float(self.body_state)  # 0.0 → retraído, 1.0 → estendido
        ox = int(self.visual_offset.x())
        oy = int(self.visual_offset.y())

        # 1. Carcaça (fixa)
        self.draw_pixmap(painter, QPointF(ox, oy), self._body_pixmap)

        # 2. Haste — translada para a direita conforme t aumenta
        rod_x = int(_ROD_OFFSET.x() + _ROD_X_RETRACTED + t * _ROD_DELTA)
        rod_y = int(_ROD_OFFSET.y())
        self.draw_pixmap(painter, QPointF(ox + rod_x, oy + rod_y), self._rod_pixmap)

    # ── propriedades ──────────────────────────────────────────────────────────

    def build_properties_dialog(self):
        dialog = super().build_properties_dialog()

        if self.domain == "hydraulic":
            dialog._field_bore      = dialog.add_number_field(
                "Diâmetro do furo (m)",  placeholder="ex: 0.05",
                value=self.properties.get("bore"), required=True)
            dialog._field_rod       = dialog.add_number_field(
                "Diâmetro da haste (m)", placeholder="ex: 0.025",
                value=self.properties.get("rod_diameter"), required=True)
            dialog._field_stroke    = dialog.add_number_field(
                "Curso (m)",             placeholder="ex: 0.5",
                value=self.properties.get("stroke"), required=True)
            dialog._field_ext_force = dialog.add_number_field(
                "Carga externa (N)",     placeholder="ex: 0.0",
                value=self.properties.get("external_force", 0.0))
        else:
            dialog._field_bore = dialog._field_stroke = None
            dialog._field_rod  = None
            dialog._field_ext_force = None

        return dialog

    def apply_properties_from_dialog(self, dialog):
        super().apply_properties_from_dialog(dialog)

        if dialog._field_bore is not None:
            for field, key in [
                (dialog._field_bore,      "bore"),
                (dialog._field_rod,       "rod_diameter"),
                (dialog._field_stroke,    "stroke"),
                (dialog._field_ext_force, "external_force"),
            ]:
                text = field.text().strip()
                self.properties[key] = float(text) if text else None