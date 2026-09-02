"""Graphics node for the relay coil."""

from PyQt6.QtCore import QCoreApplication

from graphics.items.base.nodes.coil.coil_item import CoilItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from simulation.nodes.coil import Coil

class RelayCoil(CoilItem):
    node_type = "relay_coil"
    simulation_cls = Coil
    SPRITE_PATH = "resources/nodes/relay_coil/relay_coil.png"
    PREFIX = "K"
    SENSOR_TYPE = "relay_coil"

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("electric",),
            sprite=cls.SPRITE_PATH,
            name=QCoreApplication.translate("RelayCoil", "Relay Coil"),
        )
