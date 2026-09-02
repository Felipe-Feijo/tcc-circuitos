"""Single-acting cylinder graphics node."""

from PyQt6.QtCore import QPointF, QCoreApplication
from PyQt6.QtGui import QPixmap
from graphics.anchors.anchor import AnchorItem
from graphics.items.base.nodes.cylinder.cylinder_item import CylinderItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from simulation.nodes.cylinder.single_acting_cylinder import SingleActingCylinder as SingleActingCylinderNode

_BASE_PATH = "resources/nodes/single_acting_cylinder"

# Rod's X positions in the body's space (in pixels)
_ROD_X_RETRACTED = 174
_ROD_X_EXTENDED  = 46
_ROD_DELTA       = _ROD_X_RETRACTED - _ROD_X_EXTENDED  # 128px

# Spring dimensions
_SPRING_W_EXTENDED  = 209   # expanded spring (rod retracted)
_SPRING_W_RETRACTED = 78    # compressed spring (rod extended)
_SPRING_W_DELTA     = _SPRING_W_EXTENDED - _SPRING_W_RETRACTED

# Offsets relative to the body's (0, 0) -- TODO: adjust once the sprites exist
_ROD_OFFSET    = QPointF(0, 0)
_SPRING_OFFSET = QPointF(85, 0)


class SingleActingCylinder(CylinderItem):
    node_type = "single_acting_cylinder"
    simulation_cls = SingleActingCylinderNode

    BODY_VISUALS = {
        0: {
            "sprite": f"{_BASE_PATH}/single_acting_cylinder_retracted.png",
            "offset": QPointF(0, 0),
        },
        1: {
            "sprite": f"{_BASE_PATH}/single_acting_cylinder_extended.png",
            "offset": QPointF(0, 0),
        }
    }

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("pneumatic", "hydraulic"),
            sprite=f"{_BASE_PATH}/single_acting_cylinder_retracted.png",
            name=QCoreApplication.translate("SingleActingCylinder", "Single Acting Cylinder"),
        )

    def setup(self) -> None:
        super().setup()
        if self.domain == "hydraulic":
            # friction doesn't appear in the dialog -- fixed at 0 in the simulation node
            self.properties.setdefault("external_force", 0.0)
            self._rod_pixmap    = QPixmap(f"{_BASE_PATH}/single_acting_cylinder_rod.png")
            self._body_pixmap   = QPixmap(f"{_BASE_PATH}/single_acting_cylinder_body.png")
            self._spring_pixmap = QPixmap(f"{_BASE_PATH}/single_acting_cylinder_spring.png")

    def initialize_anchors(self):
        self.add_anchor(AnchorItem(
            "A",
            QPointF(self.width * 18 / 360, self.height),
            node=self,
            domain=self.domain,
            exit_directions={"external": ["bottom"]}
        ))

    # -- painting -----------------------------------------------------------------

    def update_body_visuals(self):
        if self.domain != "hydraulic":
            super().update_body_visuals()
            return

    def paint_body(self, painter):
        if self.domain != "hydraulic":
            super().paint_body(painter)
            return

        t  = float(self.body_state)  # 0.0 -> retracted, 1.0 -> extended
        ox = int(self.visual_offset.x())
        oy = int(self.visual_offset.y())

        # 1. Housing (fixed)
        painter.drawPixmap(ox, oy, self._body_pixmap)

        # 2. Spring -- scales horizontally (expanded when retracted, compressed when extended)
        spring_w = int(_SPRING_W_RETRACTED + (1.0 - t) * _SPRING_W_DELTA)
        spring_scaled = self._spring_pixmap.scaled(
            spring_w,
            self._spring_pixmap.height()
        )
        # anchors on the right: shifts x as the spring shrinks
        spring_x = int(_SPRING_OFFSET.x() + (_SPRING_W_EXTENDED - spring_w))
        painter.drawPixmap(
            ox + spring_x,
            oy + int(_SPRING_OFFSET.y()),
            spring_scaled
        )

        # 3. Rod -- translates left as t increases
        rod_x = int(_ROD_OFFSET.x() + _ROD_X_RETRACTED - (1-t) * _ROD_DELTA)
        rod_y = int(_ROD_OFFSET.y())
        painter.drawPixmap(ox + rod_x, oy + rod_y, self._rod_pixmap)

    # -- properties -----------------------------------------------------------------

    def build_properties_dialog(self):
        dialog = super().build_properties_dialog()

        if self.domain == "hydraulic":
            dialog._field_bore      = dialog.add_number_field(
                self.tr("Bore diameter (m)"),            placeholder="ex: 0.05",
                value=self.properties.get("bore"), required=True)
            dialog._field_stroke    = dialog.add_number_field(
                self.tr("Stroke (m)"),                        placeholder="ex: 0.5",
                value=self.properties.get("stroke"), required=True)
            dialog._field_spring_k  = dialog.add_number_field(
                self.tr("Spring constant (N/m)"),          placeholder="ex: 5000",
                value=self.properties.get("spring_k"), required=True)
            dialog._field_ext_force = dialog.add_number_field(
                self.tr("External load (N)"),                placeholder="ex: 0.0",
                value=self.properties.get("external_force", 0.0))
        else:
            dialog._field_bore = dialog._field_stroke = None
            dialog._field_spring_k = dialog._field_ext_force = None

        return dialog

    def apply_properties_from_dialog(self, dialog):
        super().apply_properties_from_dialog(dialog)

        if dialog._field_bore is not None:
            for field, key in [
                (dialog._field_bore,      "bore"),
                (dialog._field_stroke,    "stroke"),
                (dialog._field_spring_k,  "spring_k"),
                (dialog._field_ext_force, "external_force"),
            ]:
                text = field.text().strip()
                self.properties[key] = float(text) if text else None