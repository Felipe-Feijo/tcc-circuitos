"""Nó de junção: ponto de derivação criado ao ligar uma conexão no meio de
outra já existente. Quase invisível -- não desenha corpo próprio, só
hospeda o anchor "J" onde 3+ conexões se encontram. A bolinha em si é
desenhada pelo próprio AnchorItem (ver AnchorItem.refresh_junction_dot),
não por este nó."""

from PyQt6.QtCore import QPointF, QRectF

from simulation.nodes.nodes import Junction
from graphics.items.base.nodes.node_item import NodeItem
from ....anchors.anchor import AnchorItem

_ALL_DIRECTIONS = ["right", "left", "top", "bottom"]


class JunctionNodeItem(NodeItem):
    node_type = "junction"
    simulation_cls = Junction

    # Raio da área de clique/arrasto ao redor do anchor "J" -- sem corpo
    # visível próprio, mas precisa de geometria não-nula pro Qt aceitar
    # seleção/drag (ItemIsMovable já vem True de NodeItem.__init__, mas
    # não tem efeito nenhum sem hit test).
    _HIT_RADIUS = 10

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

    def boundingRect(self) -> QRectF:
        """Centrado na origem local (onde o anchor "J" está), não no
        canto como NodeItem.boundingRect() (QRectF(0,0,width,height))
        faria -- assim node.pos() continua sendo exatamente a posição do
        anchor, sem exigir nenhuma mudança em split_connection_at's
        setPos(point)."""
        r = self._HIT_RADIUS
        return QRectF(-r, -r, 2 * r, 2 * r)
