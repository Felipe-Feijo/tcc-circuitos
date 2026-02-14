from graphics.items.base.nodes.coil.coil_item import CoilItem

class RelayCoil(CoilItem):
    SPRITE_PATH = "resources/nodes/relay_coil/relay_coil.png"
    PREFIX = "K"
    SENSOR_TYPE = "relay_coil"
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.node_type = "relay_coil"