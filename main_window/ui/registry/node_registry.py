from graphics.items.base.nodes.coil.relay_coil import RelayCoil
from graphics.items.base.nodes.expandable.ground import Ground
from graphics.items.base.nodes.expandable.voltage_source import VoltageSource
from graphics.items.base.nodes.fixed_displacement_pump import FixedDisplacementPump
from graphics.items.base.nodes.direct_operated_relief_valve import DirectOperatedReliefValve
from graphics.items.base.nodes.node_descriptor import NodeDescriptor

from graphics.items.base.nodes.logic_valve.or_valve import OrValve
from graphics.items.base.nodes.logic_valve.and_valve import AndValve
from graphics.items.base.nodes.expandable.pressure_line import PressureLine
from graphics.items.base.nodes.pressure_source import PressureSource
from graphics.items.base.nodes.cylinder.single_acting_cylinder import SingleActingCylinder
from graphics.items.base.nodes.cylinder.double_acting_cylinder import DoubleActingCylinder
from graphics.items.base.nodes.exhaust import Exhaust

from graphics.items.base.nodes.directional_valve.valve_3_2_ways import Valve_3_2_Ways
from graphics.items.base.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways
from graphics.items.base.nodes.directional_valve.valve_5_2_ways import Valve_5_2_Ways


from graphics.items.base.nodes.coil.solenoid_coil import SolenoidCoil
from graphics.items.base.nodes.reservoir import Reservoir
from graphics.items.base.nodes.switch.button_switch import ButtonSwitch
from graphics.items.base.nodes.switch.relay_switch import RelaySwitch
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
        name="Valve_5_2_Ways",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/valve_5_2_ways/valve_5_2_body_right.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(Valve_5_2_Ways, domain=domain))
    )
    pneumatic.add_node(
        name="SingleActingCylinder",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/single_acting_cylinder/single_acting_cylinder_retracted.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(SingleActingCylinder, domain=domain))
    )
    pneumatic.add_node(
        name="DoubleActingCylinder",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/double_acting_cylinder/double_acting_cylinder_retracted.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(DoubleActingCylinder, domain=domain))
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
    pneumatic.add_node(
        name="AndValve",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/and_valve/and_valve_default.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(AndValve, domain=domain))
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
    electric.add_node(
        name="RelaySwitch",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/relay_switch/relay_switch_no_open.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(RelaySwitch, domain=domain))
    )
    electric.add_node(
        name="SolenoidCoil",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/solenoid_coil/solenoid_coil.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(SolenoidCoil, domain=domain))
    )
    electric.add_node(
        name="RelayCoil",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/relay_coil/relay_coil.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(RelayCoil, domain=domain))
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
    hydraulic.add_node(
        name="Reservoir",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/reservoir/reservoir.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(Reservoir, domain=domain))
    )
    hydraulic.add_node(
        name="FixedDisplacementPump",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/fixed_displacement_pump/fixed_displacement_pump.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(FixedDisplacementPump, domain=domain))
    )
    hydraulic.add_node(
        name="ReliefValve (direct)",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/direct_operated_relief_valve/direct_operated_relief_valve.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(DirectOperatedReliefValve, domain=domain))
    )
    hydraulic.add_node(
        name="SingleActingCylinder",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/single_acting_cylinder/single_acting_cylinder_retracted.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(SingleActingCylinder, domain=domain))
    )
    hydraulic.add_node(
        name="DoubleActingCylinder",
        pixmap=generate_pixmap_for_palette(
            "resources/nodes/double_acting_cylinder/double_acting_cylinder_retracted.png"
        ),
        callback=lambda: on_add_node(NodeDescriptor(DoubleActingCylinder, domain=domain))
    )
    # Adicione nós hidráulicos aqui usando hydraulic.add_node(...)