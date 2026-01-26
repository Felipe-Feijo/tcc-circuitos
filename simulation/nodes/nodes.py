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

    def handle_command(self, command: dict):
        if command["type"] == "button":
            if command["action"] == "press":
                self.button_pressed = True
            elif command["action"] == "release":
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
    

class Valve_4_2_Ways(Node):
    def __init__(self, node_id, actuators=None):
        super().__init__(node_id, "valve_4_2_ways")

        # Anchors
        self.add_anchor("P")
        self.add_anchor("A")
        self.add_anchor("B")
        self.add_anchor("R")
        self.add_anchor("PL")
        self.add_anchor("PR")

        # Bits do item gráfico
        self.bits = {"left": 0, "right": 0}

        self.actuators = actuators or {}

        # Estado atual da válvula (conexão ativa)
        # Representa qual lado do corpo está ativo
        self.body_state = 0  # 0 = repouso, 1 = ativo

    def handle_command(self, command: dict):
        """
        command: 'press' ou 'release'
        side: 'left' ou 'right'
        """

        if command["type"] == "button":
            if command["side"] not in self.bits:
                return

            if command["action"] == "press":
                self.bits[command["side"]] = 1
            elif command["action"] == "release":
                self.bits[command["side"]] = 0

    def update(self):
        """Atualiza estado interno da válvula."""

        # --- mola: força o lado se o outro não estiver atuado ---
        for side, actuators in self.actuators.items():
            if actuators is None:
                continue
            
            other = "right" if side == "left" else "left"
            
            if "pilot" in actuators:
                anchor_name = "PL" if side == "left" else "PR"
                self.bits[side] = 1 if self.anchors[anchor_name].pressurized else 0



            if "spring" in actuators and "spring" not in self.actuators.get(other, []):
                self.bits[side] = 0 if self.bits[other] else 1

        # --- lógica do corpo (igual à gráfica) ---
        if (self.bits["left"], self.bits["right"]) == (1, 0):
            self.body_state = 1  # ativa
        elif (self.bits["left"], self.bits["right"]) == (0, 1):
            self.body_state = 0  # desativa
        # 00 e 11 → mantém

    def get_internal_connections(self):
        """Retorna pares de anchors conectados internamente."""
        if self.body_state == 0:
            return [("P", "A"), ("B", "R")]
        else:
            return [("P", "B"), ("A", "R")]
        
