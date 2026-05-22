"""Nó gráfico de bobina de relé."""

from graphics.items.base.nodes.coil.coil_item import CoilItem
from simulation.nodes.coil import Coil

class RelayCoil(CoilItem):
    node_type = "relay_coil"
    simulation_cls = Coil
    SPRITE_PATH = "resources/nodes/relay_coil/relay_coil.png"
    PREFIX = "K"
    SENSOR_TYPE = "relay_coil"
