"""Graphics node for the pressure gauge (hydraulic and pneumatic).

Purely passive tap -- see simulation/nodes/pressure_gauge.py for the
domain-specific reading behavior.
"""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QCoreApplication
from simulation.nodes.pressure_gauge import PressureGauge as PressureGaugeNode

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from ....anchors.anchor import AnchorItem


class PressureGauge(NodeItem):
    node_type = "pressure_gauge"
    simulation_cls = PressureGaugeNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("hydraulic", "pneumatic"),
            sprite="resources/nodes/pressure_gauge/pressure_gauge.png",
            name=QCoreApplication.translate("PressureGauge", "Pressure Gauge"),
        )

    def setup(self) -> None:
        self.pixmap = QPixmap("resources/nodes/pressure_gauge/pressure_gauge.png")
        self.width  = self.pixmap.width()
        self.height = self.pixmap.height()

        self.add_anchor(AnchorItem(
            "P",
            QPointF(self.width * 0.5, self.height),
            node=self,
            domain=self.domain,
            exit_directions={"external": ["bottom", "right", "left"]},
        ))
