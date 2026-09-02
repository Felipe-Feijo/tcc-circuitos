"""Graphics node for the direct-acting relief valve (sequence valve when
piloted).

Sprite layout
-------------
Width x Height: 200 x 162 px
Anchor P (top)   : (width*99/199, 0)          exit -> top
Anchor T (base)  : (width*99/199, height)     exit -> bottom
Anchor Y (pilot) : (width, height*53.5/162)   exit -> right
                   present only when properties["piloted"] is True.
                   Height measured on the relief_valve_pilot.png overlay:
                   the dotted line touches the right edge (x=199) between
                   y=51 and y=56 -- 53.5 is the center of that interval,
                   not height/2 (which would land much lower, at the
                   middle of the body).

Sprites
-------
relief_valve.png       -- body (without adjustable spring arrow)
relief_valve_pilot.png -- external pilot overlay (dotted line + Y port),
                          drawn on top of the body when piloted=True.
"""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QCoreApplication
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
            name=QCoreApplication.translate("ReliefValve", "Relief Valve (direct)"),
        )

    def setup(self) -> None:
        self.properties = {"piloted": False}
        self.pixmap = QPixmap(f"{_SPRITE_DIR}/relief_valve.png")
        self.width  = self.pixmap.width()
        self.height = self.pixmap.height()

        self.add_anchor(AnchorItem("T", QPointF(self.width*99/199, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))
        self.add_anchor(AnchorItem("P", QPointF(self.width*99/199, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))

        self._pixmap_pilot = QPixmap(f"{_SPRITE_DIR}/relief_valve_pilot.png")
        self._pilot_overlay = None
        self._update_pilot_anchor()

    def _update_pilot_anchor(self) -> None:
        """Adds/removes the Y anchor and the pilot overlay based on
        self.properties. Called in setup() and whenever the property
        changes (apply_properties / apply_properties_from_dialog)."""
        if self.properties.get("piloted"):
            self.add_anchor(AnchorItem(
                "Y", QPointF(self.width, self.height * 53.5 / 162), node=self, domain=self.domain,
                exit_directions={"external": ["right"]},
            ))
            self._pilot_overlay = self._pixmap_pilot
        else:
            self.remove_anchor("Y")
            self._pilot_overlay = None

    def apply_properties(self) -> None:
        self._update_pilot_anchor()
        self.update()

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self._pilot_overlay is not None:
            painter.save()
            painter.translate(self._visual_offset)
            self.draw_pixmap(painter, QPointF(0, 0), self._pilot_overlay)
            painter.restore()

    def build_properties_dialog(self):
        dialog = PropertiesDialog(title=self.tr("Relief Valve — Properties"))
        if self.domain == "hydraulic":
            dialog._field_p_set = dialog.add_number_field(
                self.tr("Cracking pressure (Pa)"), placeholder="ex: 1.5e7  (= 150 bar)",
                value=self.properties.get("p_set"),
                required=True,
            )
            dialog._field_piloted = dialog.add_bool_field(
                self.tr("External pilot (Y)"), value=self.properties.get("piloted", False),
            )
        else:
            dialog._field_p_set = None
            dialog._field_piloted = None
        return dialog

    def apply_properties_from_dialog(self, dialog):
        if dialog._field_p_set is not None:
            p_set_text = dialog._field_p_set.text().strip()
            self.properties["p_set"] = float(p_set_text) if p_set_text else None
        if dialog._field_piloted is not None:
            self.properties["piloted"] = dialog._field_piloted.isChecked()
        self._update_pilot_anchor()
        self.update()
