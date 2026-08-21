"""Graphics node for the solenoid coil."""

from graphics.items.base.nodes.coil.coil_item import CoilItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from simulation.nodes.coil import Coil

class SolenoidCoil(CoilItem):
    node_type = "solenoid_coil"
    simulation_cls = Coil
    SPRITE_PATH = "resources/nodes/solenoid_coil/solenoid_coil.png"
    PREFIX = "Y"
    SENSOR_TYPE = "solenoid_coil"

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("electric",),
            sprite=cls.SPRITE_PATH,
            name="Solenoid Coil",
        )
