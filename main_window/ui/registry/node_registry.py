from graphics.items.base.nodes.generic_valve import GenericValve
from graphics.items.base.nodes.cool_valve import CoolValve
from graphics.utils.pixmap_utils import generate_pixmap_for_palette


def register_nodes(palette, on_add_node):
    palette.add_node(
        name="Generic_valve",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/generic_valve/generic_valve.png"
        ),
        callback=lambda: on_add_node(GenericValve)
    )
    palette.add_node(
        name="Cool_valve",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/cool_valve/cool_valve.png"
        ),
        callback=lambda: on_add_node(CoolValve)
    )