"""Graphic node for the check valve (pneumatic and hydraulic).

Sprite layout
-------------
Width x Height: 150 x 150 px
Anchor X (left)  : (0, 75)      exit -> left
Anchor Y (right) : (150, 75)    exit -> right
Anchor Z (pilot) : (150, 42) by default
                   (150, 108) if properties["pilot_mirrored"] is True
                   present only when properties["piloted"] is True

Note: "pilot_mirrored" is relative to the sprite (local coordinate), not
the screen -- unlike "top"/"bottom" labels, it stays correct after the
component is rotated (NodeItem rotation already rotates the anchor and
overlay together, so a screen-absolute label would be misleading).

Sprites
-------
check_valve_open.png    -- corpo, Y=1 (fluxo livre passando)
check_valve_closed.png  -- corpo, Y=0
check_valve_pilot.png   -- pilot overlay (frame + dotted tail leaving
                           from the right side, curving toward the top
                           by default). Drawn on top of the body when
                           piloted=True. Mirrored vertically
                           (QTransform().scale(1, -1)) when
                           pilot_mirrored=True.
"""

from PyQt6.QtGui import QPixmap, QTransform
from PyQt6.QtCore import QPointF, QCoreApplication

from simulation.nodes.check_valve.check_valve import (
    CheckValve as CheckValveNode,
)
from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.utils.properties_dialog import PropertiesDialog
from .....anchors.anchor import AnchorItem

_SPRITE_DIR = "resources/nodes/check_valve"

_PILOT_ANCHOR_Y = {False: 42, True: 108}


class CheckValve(NodeItem):
    node_type = "check_valve"
    simulation_cls = CheckValveNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("pneumatic", "hydraulic"),
            sprite=f"{_SPRITE_DIR}/check_valve_closed.png",
            name=QCoreApplication.translate("CheckValve", "Check Valve"),
        )

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def setup(self) -> None:
        self.properties = {"piloted": False, "pilot_mirrored": False}

        self._pixmap_open   = QPixmap(f"{_SPRITE_DIR}/check_valve_open.png")
        self._pixmap_closed = QPixmap(f"{_SPRITE_DIR}/check_valve_closed.png")
        self._pixmap_pilot  = QPixmap(f"{_SPRITE_DIR}/check_valve_pilot.png")

        self.pixmap = self._pixmap_closed
        self.width  = self.pixmap.width()   # 150
        self.height = self.pixmap.height()  # 150

        self.add_anchor(AnchorItem(
            "X", QPointF(0, self.height / 2), node=self, domain=self.domain,
            exit_directions={"external": ["left"]},
        ))
        self.add_anchor(AnchorItem(
            "Y", QPointF(self.width, self.height / 2), node=self, domain=self.domain,
            exit_directions={"external": ["right"]},
        ))

        self._pilot_overlay = None
        self._update_pilot_anchor()

    def _update_pilot_anchor(self) -> None:
        """Adds/removes the Z anchor and the pilot overlay based on
        self.properties. Called in setup() and whenever the property
        changes (apply_properties / apply_properties_from_dialog)."""
        if self.properties.get("piloted"):
            mirrored = self.properties.get("pilot_mirrored", False)
            anchor_y = _PILOT_ANCHOR_Y[mirrored]
            self.add_anchor(AnchorItem(
                "Z", QPointF(self.width, anchor_y), node=self, domain=self.domain,
                exit_directions={"external": ["right"]},
            ))
            self._pilot_overlay = (
                self._pixmap_pilot.transformed(QTransform().scale(1, -1)) if mirrored
                else self._pixmap_pilot
            )
        else:
            self.remove_anchor("Z")
            self._pilot_overlay = None

    def apply_properties(self) -> None:
        self._update_pilot_anchor()
        self.update()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self._pilot_overlay is not None:
            painter.save()
            painter.translate(self._visual_offset)
            self.draw_pixmap(painter, QPointF(0, 0), self._pilot_overlay)
            painter.restore()

    # ------------------------------------------------------------------
    # Simulation visual sync
    # ------------------------------------------------------------------

    def update_from_domain(self, domain_node) -> None:
        super().update_from_domain(domain_node)
        visual = domain_node.get_visual_state()
        self.pixmap = self._pixmap_closed if visual == "closed" else self._pixmap_open
        self.update()

    def reset_visual_state(self) -> None:
        super().reset_visual_state()
        self.pixmap = self._pixmap_closed
        self.update()

    # ------------------------------------------------------------------
    # Properties dialog (implementado na Task 4)
    # ------------------------------------------------------------------

    def build_properties_dialog(self) -> PropertiesDialog:
        dialog = PropertiesDialog(title="Check Valve — Properties")

        dialog._field_piloted = dialog.add_bool_field(
            "Piloted", value=self.properties.get("piloted", False),
        )
        dialog._field_pilot_mirrored = dialog.add_bool_field(
            "Mirror pilot side", value=self.properties.get("pilot_mirrored", False),
        )

        def _set_pilot_mirrored_visible(visible: bool) -> None:
            form = dialog._form_layout
            for row in range(form.rowCount()):
                item = form.itemAt(row, form.ItemRole.FieldRole)
                if item and item.widget() is dialog._field_pilot_mirrored:
                    form.setRowVisible(row, visible)
                    return

        dialog._field_piloted.toggled.connect(_set_pilot_mirrored_visible)
        _set_pilot_mirrored_visible(dialog._field_piloted.isChecked())

        return dialog

    def apply_properties_from_dialog(self, dialog: PropertiesDialog) -> None:
        self.properties["piloted"] = dialog._field_piloted.isChecked()
        self.properties["pilot_mirrored"] = dialog._field_pilot_mirrored.isChecked()
        self._update_pilot_anchor()
        self.update()
