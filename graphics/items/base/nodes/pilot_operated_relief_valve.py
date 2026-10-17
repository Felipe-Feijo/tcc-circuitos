"""Graphics node for the pilot-operated relief valve (vent port X).

Sprite layout
-------------
Width x Height: 254 x 161 px
Anchor P (top)   : (width*98.5/254, 0)        exit -> top
Anchor T (base)  : (width*98.5/254, height)   exit -> bottom
Anchor X (vent)  : (width, height*19.5/161)   exit -> right
Measured on the PNGs: P/T opaque pixels on the top/bottom rows at
x=97..100; the X line's last dash touches the right edge at y=17..22.

Sprites
-------
pilot_operated_relief_valve.png        -- body, X line open
pilot_operated_relief_valve_x_plug.png -- plug bar only, drawn while X
                                          has no connection (unconnected
                                          X is plugged in the solver too)
"""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QCoreApplication
from simulation.nodes.pilot_operated_relief_valve import (
    PilotOperatedReliefValve as PilotOperatedReliefValveNode,
)

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.utils.properties_dialog import PropertiesDialog
from graphics.utils.defect_dialog import DefectFieldSpec
from ....anchors.anchor import AnchorItem

_SPRITE_DIR = "resources/nodes/pilot_operated_relief_valve"


class _VentAnchor(AnchorItem):
    """Repaints the node when X gains/loses a connection (plug overlay)."""

    def refresh_junction_dot(self) -> None:
        super().refresh_junction_dot()
        if self.node is not None:
            self.node.update()


class PilotOperatedReliefValve(NodeItem):
    node_type = "pilot_operated_relief_valve"
    simulation_cls = PilotOperatedReliefValveNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("hydraulic",),
            sprite=f"{_SPRITE_DIR}/pilot_operated_relief_valve.png",
            name=QCoreApplication.translate("PilotOperatedReliefValve", "Relief Valve (pilot-operated)"),
        )

    def setup(self) -> None:
        self.properties = {}
        self.pixmap = QPixmap(f"{_SPRITE_DIR}/pilot_operated_relief_valve.png")
        self._pixmap_plug = QPixmap(f"{_SPRITE_DIR}/pilot_operated_relief_valve_x_plug.png")
        self.width = self.pixmap.width()
        self.height = self.pixmap.height()

        x_pt = self.width * 98.5 / 254
        self.add_anchor(AnchorItem("T", QPointF(x_pt, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))
        self.add_anchor(AnchorItem("P", QPointF(x_pt, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))
        self.add_anchor(_VentAnchor("X", QPointF(self.width, self.height * 19.5 / 161), node=self, domain=self.domain, exit_directions={"external": ["right"]}))

    def x_plugged(self) -> bool:
        anchor = self.anchors.get("X")
        return anchor is not None and anchor.connection_count() == 0

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.x_plugged():
            painter.save()
            painter.translate(self._visual_offset)
            self.draw_pixmap(painter, QPointF(0, 0), self._pixmap_plug)
            painter.restore()

    def build_properties_dialog(self):
        dialog = PropertiesDialog(title=self.tr("Pilot-Operated Relief Valve — Properties"))
        dialog._field_p_set = dialog.add_number_field(
            self.tr("Pilot setting p_set (Pa)"), placeholder="ex: 1e7  (= 100 bar)",
            value=self.properties.get("p_set"),
            required=True,
        )
        dialog._field_p_vent = dialog.add_number_field(
            self.tr("Main-stage spring p_vent (Pa)"), placeholder="3e5  (= 3 bar, default)",
            value=self.properties.get("p_vent"),
        )
        return dialog

    def apply_properties_from_dialog(self, dialog):
        p_set_text = dialog._field_p_set.text().strip()
        self.properties["p_set"] = float(p_set_text) if p_set_text else None
        p_vent_text = dialog._field_p_vent.text().strip()
        if p_vent_text:
            self.properties["p_vent"] = float(p_vent_text)
        else:
            self.properties.pop("p_vent", None)
        self.update()

    def defect_fields(self):
        if self.domain != "hydraulic":
            return []
        return [DefectFieldSpec(
            "p_set", self.tr("Pilot setting p_set (Pa)"), "number",
            placeholder="ex: 1e7  (= 100 bar)", min_value=0,
        )]
