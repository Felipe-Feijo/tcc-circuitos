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
    
class Valve3_2(Node):
    def __init__(self, node_id):
        super().__init__(node_id=node_id, node_type="valve_3_2_ways")

        # Anchors pneumáticos
        self.add_anchor("P")
        self.add_anchor("A")
        self.add_anchor("R")

        # Estado interno (FSM)
        # 0 = repouso (mola)
        # 1 = acionada (botão)
        self.state = 0

        # Sinais de controle (vindos da UI / engine)
        self.button_pressed = False

    def handle_command(self, command: str):
        if command == "press":
            self.button_pressed = True
        elif command == "release":
            self.button_pressed = False

    # -------------------------
    # Interface de controle
    # -------------------------

    def set_button(self, pressed: bool):
        self.button_pressed = pressed

    # -------------------------
    # Atualização da FSM
    # -------------------------

    def update(self):
        """
        Atualiza o estado interno da válvula
        com base nos sinais de controle.
        """
        if self.button_pressed:
            self.state = 1
        else:
            self.state = 0

    # -------------------------
    # Conectividade interna
    # -------------------------

    def get_internal_connections(self):
        """
        Retorna pares de anchors que estão conectados
        internamente neste estado.
        """
        if self.state == 0:
            # Repouso: A -> R
            return [("A", "R")]

        elif self.state == 1:
            # Acionada: P -> A
            return [("P", "A")]

        return []
    
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
        
