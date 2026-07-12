"""Nó gráfico de válvula lógica OR (seletor de circuito)."""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QRectF
from simulation.nodes.logic_valve.or_valve import OrValve as OrValveNode

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from .....anchors.anchor import AnchorItem


class OrValve(NodeItem):
    node_type = "or_valve"
    simulation_cls = OrValveNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("pneumatic",),
            sprite="resources/nodes/or_valve/or_valve_x_side.png",
            name="Or Valve",
        )

    def setup(self) -> None:
        self.icon_x_side = QPixmap("resources/nodes/or_valve/or_valve_x_side.png")
        self.icon_y_side = QPixmap("resources/nodes/or_valve/or_valve_y_side.png")

        self.pixmap = self.icon_x_side
        self.width  = self.pixmap.width()
        self.height = self.pixmap.height()

        # Mesma proporção da AndValve (graphics/items/base/nodes/
        # logic_valve/and_valve.py) -- o sprite da OrValve passou a usar a
        # mesma base/tamanho da AndValve, então os anchors seguem as
        # mesmas frações de width/height (X/Y a 90/165 da altura, A
        # centralizado no topo).
        self.add_anchor(AnchorItem("X", QPointF(0, self.height * 90/165), node=self, domain=self.domain, exit_directions={"external": ["left"]}))
        self.add_anchor(AnchorItem("Y", QPointF(self.width, self.height * 90/165), node=self, domain=self.domain, exit_directions={"external": ["right"]}))
        self.add_anchor(AnchorItem("A", QPointF(self.width * 0.5, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))

    def reset_visual_state(self) -> None:
        # OrValve has no icon_default — x_side is the resting state
        super().reset_visual_state()
        self.pixmap = self.icon_x_side
        self.update()


    def update_from_domain(self, domain_node):
        super().update_from_domain(domain_node)
        state = domain_node.get_visual_state()
        if state == "X":
            self.pixmap = self.icon_x_side
        elif state == "Y":
            self.pixmap = self.icon_y_side
        self.update()
            
        


    


    

