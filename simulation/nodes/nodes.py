# domain/components.py

from __future__ import annotations
from typing import Dict, List


class Anchor:
    def __init__(self, name: str, node: "Node"):
        self.node = node
        self.name = name
        self.id = (node.id, name)
        self.connections: List["Connection"] = []

        self.pressurized: bool = False
        self.is_driver = False

    def connect(self, connection: "Connection"):
        if connection not in self.connections:
            self.connections.append(connection)


class Node:
    def __init__(self, node_id, node_type):
        self.id = node_id
        self.type = node_type
        self.anchors = {}

    def add_anchor(self, name) -> Anchor:
        anchor = Anchor(name, self)
        self.anchors[name] = anchor
        return anchor

    def get_anchor(self, name):
            return self.anchors[name]

    @classmethod
    def from_node_item(cls, item):
        node = cls(item.id, item.node_type)
        for a in item.anchors:
            node.add_anchor(a.name)
        return node
    
    def handle_command(self, command: str):
        """
        External command (debug / UI / test)
        """
        pass

    def update(self):
        """
        Default update.
        Nodes without dynamics do nothing.
        """
        pass

    def get_internal_connections(self):
        """
        Default: no internal connections.
        """
        return []
    
    def get_visual_state(self):
        return None


    
class PressureSource(Node):
    def __init__(self, node_id):
        super().__init__(node_id=node_id, node_type="pressure_source")

        # Porta de saída
        anchor = self.add_anchor("P")
        anchor.pressurized = True  # pressão fixa
        anchor.is_driver = True     # marca como driver

class Exhaust(Node):
    def __init__(self, node_id):
        super().__init__(node_id=node_id, node_type="exhaust")

        # Porta de entrada
        anchor = self.add_anchor("R")
        anchor.pressurized = False  # pressão fixa
        anchor.is_driver = True     # marca como driver


    
class Piston(Node):
    def __init__(self, node_id):
        super().__init__(node_id=node_id, node_type="piston")

        # Porta pneumática única
        self.add_anchor("A")

        # Estado interno
        # 0 = retraído
        # 1 = avançado
        self.position = 0

    def update(self):
        self.position = 1 if self.anchors["A"].pressurized else 0

    def get_visual_state(self):
            return self.position

class OrValve(Node):
    def __init__(self, node_id):
        super().__init__(node_id=node_id, node_type="or_valve")

        # Anchors pneumáticos
        self.add_anchor("X")
        self.add_anchor("Y")
        self.add_anchor("A")

        # Estado interno (shuttle com memória)
        self.active_input: str = "X"  # estado inicial

    def update(self):
        x = self.anchors["X"].pressurized
        y = self.anchors["Y"].pressurized

        # Só muda se exatamente uma entrada estiver pressurizada
        if x ^ y:
            self.active_input = "X" if x else "Y"
        # else: mantém o estado atual

    def get_internal_connections(self):
        return [(self.active_input, "A")]
    
    def get_visual_state(self):
        return self.active_input  # "X" ou "Y"
    


