"""Graphic node for the check valve (pneumatic only).

Sprite layout
-------------
Width x Height: 150 x 150 px
Anchor X (left)  : (0, 75)      exit -> left
Anchor Y (right) : (150, 75)    exit -> right
Anchor Z (pilot) : (150, 42) se pilot_exit == "top" (padrão)
                   (150, 108) se pilot_exit == "bottom"
                   presente apenas quando properties["piloted"] é True

Sprites
-------
check_valve_open.png    -- corpo, Y=1 (fluxo livre passando)
check_valve_closed.png  -- corpo, Y=0
check_valve_pilot.png   -- overlay de pilotagem (moldura + rabo pontilhado
                           saindo do lado direito, curva pro topo por
                           padrão). Desenhado por cima do corpo quando
                           piloted=True. Espelhado verticalmente
                           (QTransform().scale(1, -1)) quando
                           pilot_exit == "bottom".
"""

from PyQt6.QtGui import QPixmap, QTransform
from PyQt6.QtCore import QPointF

from simulation.nodes.check_valve.check_valve import (
    CheckValve as CheckValveNode,
)
from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.utils.properties_dialog import PropertiesDialog
from .....anchors.anchor import AnchorItem

_SPRITE_DIR = "resources/nodes/check_valve"

_PILOT_ANCHOR_Y = {"top": 42, "bottom": 108}


class CheckValve(NodeItem):
    node_type = "check_valve"
    simulation_cls = CheckValveNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("pneumatic",),
            sprite=f"{_SPRITE_DIR}/check_valve_open.png",
            name="Check Valve",
        )

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def setup(self) -> None:
        self.properties = {"piloted": False, "pilot_exit": "top"}

        self._pixmap_open   = QPixmap(f"{_SPRITE_DIR}/check_valve_open.png")
        self._pixmap_closed = QPixmap(f"{_SPRITE_DIR}/check_valve_closed.png")
        self._pixmap_pilot  = QPixmap(f"{_SPRITE_DIR}/check_valve_pilot.png")

        self.pixmap = self._pixmap_open
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
        """Adiciona/remove a anchor Z e o overlay de pilotagem conforme
        self.properties. Chamado em setup() e sempre que a propriedade
        muda (apply_properties / apply_properties_from_dialog)."""
        if self.properties.get("piloted"):
            pilot_exit = self.properties.get("pilot_exit", "top")
            anchor_y = _PILOT_ANCHOR_Y[pilot_exit]
            self.add_anchor(AnchorItem(
                "Z", QPointF(self.width, anchor_y), node=self, domain=self.domain,
                exit_directions={"external": ["right"]},
            ))
            self._pilot_overlay = (
                self._pixmap_pilot if pilot_exit == "top"
                else self._pixmap_pilot.transformed(QTransform().scale(1, -1))
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
        self.pixmap = self._pixmap_open
        self.update()

    # ------------------------------------------------------------------
    # Properties dialog (implementado na Task 4)
    # ------------------------------------------------------------------

    def build_properties_dialog(self) -> PropertiesDialog:
        return None

    def apply_properties_from_dialog(self, dialog: PropertiesDialog) -> None:
        pass
