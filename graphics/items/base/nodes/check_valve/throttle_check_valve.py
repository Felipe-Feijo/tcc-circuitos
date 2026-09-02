"""Graphic node for the throttle check valve (pneumatic and hydraulic).

Sprite layout
-------------
Width × Height: 200 × 150 px
Anchor X (left) : (  0, 106/150 * height)   exit → left
Anchor Y (right): (200, 106/150 * height)   exit → right

Sprites
-------
throttle_check_valve_open.png    — default / idle / free-flow
throttle_check_valve_closed.png  — restricted direction (X=1, Y=0)
"""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QCoreApplication

from simulation.nodes.check_valve.throttle_check_valve import (
    ThrottleCheckValve as ThrottleCheckValveNode,
)
from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.utils.properties_dialog import PropertiesDialog
from .....anchors.anchor import AnchorItem

_SPRITE_DIR = "resources/nodes/throttle_check_valve"


class ThrottleCheckValve(NodeItem):
    node_type = "throttle_check_valve"
    simulation_cls = ThrottleCheckValveNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("pneumatic", "hydraulic"),
            sprite=f"{_SPRITE_DIR}/throttle_check_valve_open.png",
            name=QCoreApplication.translate("ThrottleCheckValve", "Throttle Check Valve"),
        )

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def setup(self) -> None:
        self.properties = {"delay_steps": 3}

        self._pixmap_open   = QPixmap(f"{_SPRITE_DIR}/throttle_check_valve_open.png")
        self._pixmap_closed = QPixmap(f"{_SPRITE_DIR}/throttle_check_valve_closed.png")

        self.pixmap = self._pixmap_open
        self.width  = self.pixmap.width()   # 200
        self.height = self.pixmap.height()  # 150

        anchor_y = 106 / 150 * self.height

        self.add_anchor(AnchorItem(
            "X",
            QPointF(0, anchor_y),
            node=self,
            domain=self.domain,
            exit_directions={"external": ["left"]},
        ))
        self.add_anchor(AnchorItem(
            "Y",
            QPointF(self.width, anchor_y),
            node=self,
            domain=self.domain,
            exit_directions={"external": ["right"]},
        ))

    def apply_properties(self) -> None:
        # delay_steps is a runtime-only property; nothing to rebuild visually.
        pass

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
        self.pixmap = self._pixmap_open
        self.update()

    # ------------------------------------------------------------------
    # Properties dialog
    # ------------------------------------------------------------------

    def build_properties_dialog(self) -> PropertiesDialog:
        dialog = PropertiesDialog(title="Throttle Check Valve — Properties")
        if self.domain == "hydraulic":
            dialog._field_delay = None
            dialog._field_k = dialog.add_number_field(
                "Condutância k (m³/s/√Pa) — sentido restrito",
                placeholder="ex: 1.5e-8",
                value=self.properties.get("k"),
                required=True,
            )
        else:
            dialog._field_delay = dialog.add_number_field(
                "Delay steps (restricted direction)",
                placeholder="ex: 3",
                value=self.properties.get("delay_steps", 3),
                required=True,
            )
            dialog._field_k = None
        return dialog

    def apply_properties_from_dialog(self, dialog: PropertiesDialog) -> None:
        if dialog._field_delay is not None:
            text = dialog._field_delay.text().strip()
            try:
                steps = max(1, int(float(text)))
            except (ValueError, TypeError):
                steps = 3
            self.properties["delay_steps"] = steps

        if dialog._field_k is not None:
            k_text = dialog._field_k.text().strip()
            self.properties["k"] = float(k_text) if k_text else None
