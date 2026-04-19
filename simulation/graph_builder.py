# domain/graph_builder.py

from simulation.nodes.fixed_displacement_pump import FixedDisplacementPump
from simulation.nodes.reservoir import Reservoir
from simulation.nodes.relief_valve import DirectOperatedReliefValve
from simulation.nodes.switch.relay_switch import RelaySwitch
from simulation.nodes.switch.button_switch import ButtonSwitch
from simulation.nodes.directional_valve.valve_3_2_ways import Valve_3_2_Ways
from simulation.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways
from simulation.nodes.ground import Ground
from simulation.nodes.logic_valve.or_valve import OrValve
from simulation.nodes.logic_valve.and_valve import AndValve
from simulation.nodes.nodes import PressureSource, Exhaust
from simulation.nodes.cylinder.single_acting_cylinder import SingleActingCylinder
from simulation.nodes.cylinder.double_acting_cylinder import DoubleActingCylinder
from simulation.connections import Connection
from simulation.nodes.pressure_line import PressureLine
from simulation.nodes.coil import Coil
from simulation.nodes.voltage_source import VoltageSource

NODE_FACTORY = {
    "valve_3_2_ways": Valve_3_2_Ways,
    "valve_4_2_ways": Valve_4_2_Ways,
    "pressure_source": PressureSource,
    "exhaust": Exhaust,
    "single_acting_cylinder": SingleActingCylinder,
    "double_acting_cylinder": DoubleActingCylinder,
    "or_valve": OrValve,
    "and_valve": AndValve,
    "pressure_line": PressureLine,
    "voltage_source": VoltageSource,
    "ground": Ground,
    "button_switch": ButtonSwitch,
    "relay_switch": RelaySwitch,
    "solenoid_coil": Coil,
    "relay_coil": Coil,
    "reservoir": Reservoir,
    "fixed_displacement_pump": FixedDisplacementPump,
    "direct_operated_relief_valve": DirectOperatedReliefValve,
}

class GraphBuilder:
    def __init__(self):
        self.nodes = {}
        self.connections = {}
        self.node_map = {}        # NodeItem -> DomainNode
        self.connection_map = {}  # ConnectionItem -> DomainConnection

    def add_node_from_item(self, node_item):
        node_cls = NODE_FACTORY[node_item.node_type]

        kwargs = {}
        if hasattr(node_item, "properties"):
            kwargs["properties"] = node_item.properties
        kwargs["domain"] = node_item.domain

        node = node_cls(node_item.id, **kwargs)

        # Determina a ordem das anchors
        if hasattr(node_item, "anchor_list"):
            # usa a lista ordenada
            anchor_items = node_item.anchor_list
        else:
            # fallback: dict.values(), ordem arbitrária
            anchor_items = node_item.anchors.values()

        for anchor_item in anchor_items:
            node.add_anchor(
                name=anchor_item.name,
                domain=anchor_item.domain
            )

        self.nodes[node.id] = node
        self.node_map[node_item] = node
        return node
    
    def add_connection_from_item(self, connection_item):
        """
        Create a domain Connection from a graphical ConnectionItem.
        """

        # Graphical anchor items at both ends of the connection
        source_anchor_item = connection_item.source_anchor
        target_anchor_item = connection_item.target_anchor

        # Domain nodes owning those anchors
        source_node = self.nodes[source_anchor_item.node.id]
        target_node = self.nodes[target_anchor_item.node.id]

        # Domain anchors corresponding to the graphical anchors
        source_anchor = source_node.get_anchor(source_anchor_item.name)
        target_anchor = target_node.get_anchor(target_anchor_item.name)

        # Create the domain connection (non-directional)
        connection = Connection(source_anchor, target_anchor)

        if connection.id not in self.connections:
            self.connections[connection.id] = connection
            self.connection_map[connection_item] = connection

        return self.connections[connection.id]
