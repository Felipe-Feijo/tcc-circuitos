from graphics.items.base.nodes.expandable.ground import Ground
from graphics.items.base.nodes.expandable.voltage_source import VoltageSource
from graphics.items.base.nodes.node_descriptor import NodeDescriptor

from graphics.items.base.nodes.or_valve import OrValve
from graphics.items.base.nodes.expandable.pressure_line import PressureLine
from graphics.items.base.nodes.pressure_source import PressureSource
from graphics.items.base.nodes.cylinder.single_acting_cylinder import SingleActingCylinder
from graphics.items.base.nodes.exhaust import Exhaust

from graphics.items.base.nodes.directional_valve.valve_3_2_ways import Valve_3_2_Ways
from graphics.items.base.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways


from graphics.items.base.nodes.switch.button_switch import ButtonSwitch
from graphics.utils.pixmap_utils import generate_pixmap_for_palette


def register_nodes(palette, on_add_node):

    regsiter_pneumatic_nodes(palette, on_add_node)
    register_electric_nodes(palette, on_add_node)
    register_hydraulic_nodes(palette, on_add_node)



def regsiter_pneumatic_nodes(palette, on_add_node):
    pneumatic = palette.sections["Pneumatic"]
    domain = "pneumatic"
    pneumatic.add_node(
        name="Valve_3_2_Ways",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/valve_3_2_ways/valve_3_2_body_right.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(Valve_3_2_Ways, domain=domain))
    )
    pneumatic.add_node(
        name="Valve_4_2_Ways",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/valve_4_2_ways/valve_4_2_body_right.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(Valve_4_2_Ways, domain=domain))
    )
    pneumatic.add_node(
        name="SingleActingCylinder",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/single_acting_cylinder/single_acting_cylinder_retracted.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(SingleActingCylinder, domain=domain))
    )
    pneumatic.add_node(
        name="Exhaust",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/exhaust/exhaust.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(Exhaust, domain=domain))
    )
    pneumatic.add_node(
        name="PressureSource",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/pressure_source/pressure_source.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(PressureSource, domain=domain))
    )
    pneumatic.add_node(
        name="PressureLine",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/pressure_line/pressure_line_terminal.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(PressureLine, domain=domain))
    )
    pneumatic.add_node(
        name="OrValve",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/or_valve/or_valve_x_side.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(OrValve, domain=domain))
    )

def register_electric_nodes(palette, on_add_node):
    electric = palette.sections["Electric"]
    domain = "electric"

    electric.add_node(
        name="VoltageSource",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/voltage_source/voltage_source_terminal.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(VoltageSource, domain=domain))
    )
    electric.add_node(
        name="Ground",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/ground/ground_terminal.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(Ground, domain=domain))
    )
    electric.add_node(
        name="ButtonSwitch",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/button_switch/button_switch_no_open.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(ButtonSwitch, domain=domain))
    )


def register_hydraulic_nodes(palette, on_add_node):
    hydraulic = palette.sections["Hydraulic"]
    domain = "hydraulic"
    hydraulic.add_node(
        name="Valve_3_2_Ways",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/valve_3_2_ways/valve_3_2_body_right.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(Valve_3_2_Ways, domain=domain))
    )
    # Adicione nós hidráulicos aqui usando hydraulic.add_node(...)