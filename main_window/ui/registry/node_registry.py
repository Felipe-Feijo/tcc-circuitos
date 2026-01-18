from graphics.items.base.nodes.pressure_source import PressureSource
from graphics.items.base.nodes.valve_3_2_ways import Valve_3_2_Ways
from graphics.items.base.nodes.piston import Piston
from graphics.items.base.nodes.exhaust import Exhaust

from graphics.utils.pixmap_utils import generate_pixmap_for_palette


def register_nodes(palette, on_add_node):
    palette.add_node(
        name="Valve_3_2_Ways",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/valve_3_2_ways/valve_3_2_ways.png"
        ),
        callback=lambda: on_add_node(Valve_3_2_Ways)
    )
    palette.add_node(
        name="Piston",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/piston/piston.png"
        ),
        callback=lambda: on_add_node(Piston)
    )
    palette.add_node(
        name="Exhaust",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/exhaust/exhaust.png"
        ),
        callback=lambda: on_add_node(Exhaust)
    )
    palette.add_node(
        name="PressureSource",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/pressure_source/pressure_source.png"
        ),
        callback=lambda: on_add_node(PressureSource)
    )