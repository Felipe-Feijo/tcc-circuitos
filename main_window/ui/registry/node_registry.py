from graphics.items.base.nodes.or_valve import OrValve
from graphics.items.base.nodes.pressure_source import PressureSource
from graphics.items.base.nodes.cylinder.single_acting_cylinder import SingleActingCylinder
from graphics.items.base.nodes.exhaust import Exhaust

from graphics.items.base.nodes.directional_valve.valve_3_2_ways import Valve_3_2_Ways
from graphics.items.base.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways

from graphics.utils.pixmap_utils import generate_pixmap_for_palette


def register_nodes(palette, on_add_node):
    palette.add_node(
        name="Valve_3_2_Ways",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/valve_3_2_ways/valve_3_2_body_right.png"
        ),
        callback=lambda: on_add_node(Valve_3_2_Ways)
    )
    palette.add_node(
        name="Valve_4_2_Ways",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/valve_4_2_ways/valve_4_2_body_right.png"
        ),
        callback=lambda: on_add_node(Valve_4_2_Ways)
    )
    palette.add_node(
        name="SingleActingCylinder",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/single_acting_cylinder/single_acting_cylinder_retracted.png"
        ),
        callback=lambda: on_add_node(SingleActingCylinder)
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

    palette.add_node(
        name="OrValve",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/or_valve/or_valve_x_side.png"
        ),
        callback=lambda: on_add_node(OrValve)
    )