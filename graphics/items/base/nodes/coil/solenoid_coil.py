from graphics.items.base.nodes.coil.coil_item import CoilItem
from simulation.nodes.coil import Coil

class SolenoidCoil(CoilItem):
    node_type = "solenoid_coil"
    simulation_cls = Coil
    SPRITE_PATH = "resources/nodes/solenoid_coil/solenoid_coil.png"
    PREFIX = "Y"
    SENSOR_TYPE = "solenoid_coil"
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.node_type = "solenoid_coil"