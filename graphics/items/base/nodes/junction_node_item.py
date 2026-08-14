"""Nó de junção: ponto de derivação criado ao ligar uma conexão no meio de
outra já existente. Quase invisível -- não desenha corpo (boundingRect
0x0), só existe pra hospedar o anchor "J" onde 3+ conexões se encontram.
A bolinha em si é desenhada pelo próprio AnchorItem (ver
AnchorItem.refresh_junction_dot), não por este nó."""

from PyQt6.QtCore import QPointF

from simulation.nodes.nodes import Junction
from graphics.items.base.nodes.node_item import NodeItem
from ....anchors.anchor import AnchorItem

_ALL_DIRECTIONS = ["right", "left", "top", "bottom"]


class JunctionNodeItem(NodeItem):
    node_type = "junction"
    simulation_cls = Junction

    def setup(self) -> None:
        self.width = 0.0
        self.height = 0.0
        self.add_anchor(AnchorItem(
            "J",
            QPointF(0, 0),
            node=self,
            domain=self.domain,
            exit_directions={
                "external": list(_ALL_DIRECTIONS),
                "internal": list(_ALL_DIRECTIONS),
            },
        ))
