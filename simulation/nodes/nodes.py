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
    def __init__(self, node_id, node_type, **kwargs):
        self.id = node_id
        self.type = node_type
        self.anchors = {}

        self.domain = kwargs.pop("domain", None)
        print(self.domain)

        self.properties = kwargs.pop("properties", {}) or {}

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
    
    def get_state(self) -> dict:
        return {
            "anchors": {
                name: anchor.pressurized
                for name, anchor in self.anchors.items()
            }
        }

    def set_state(self, state: dict):
        anchor_states = state.get("anchors", {})
        for name, pressurized in anchor_states.items():
            if name in self.anchors:
                self.anchors[name].pressurized = pressurized

    def handle_command(self, command: str):
        """
        External command (debug / UI / test)
        """
        pass

    def update(self, outputs=None):
        """
        Default update.
        Nodes without dynamics do nothing.
        """
        pass

    def post_step_update(self):
        """
        Executado UMA vez após estabilização.
        - sensores
        - delays
        - commits de estado físico
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
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id=node_id, node_type="pressure_source", **kwargs)

        # Porta de saída
        anchor = self.add_anchor("P")
        anchor.pressurized = True  # pressão fixa
        anchor.is_driver = True     # marca como driver

class Exhaust(Node):
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id=node_id, node_type="exhaust", **kwargs)

        # Porta de entrada
        anchor = self.add_anchor("R")
        anchor.pressurized = False  # pressão fixa
        anchor.is_driver = True     # marca como driver


    
class SingleActingCylinder(Node):
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id=node_id, node_type="single_acting_cylinder", **kwargs)

        # Porta pneumática única
        self.add_anchor("A")

        # Estado interno
        # 0 = retraído
        # 1 = avançado
        self.position = 0

        # Extrai apenas o que precisa
        self.sensors = self.properties.get("sensors", {
            "retracted": {"type": None, "name": ""},
            "extended": {"type": None, "name": ""}
        })

        self.outputs = {}

    def update(self, outputs=None):
        self.position = 1 if self.anchors["A"].pressurized else 0

    def post_step_update(self):
        if self.sensors["retracted"]["type"]:
            name = self.sensors["retracted"]["name"]
            self.outputs[name] = {
                "type": "signal",
                "value": self.position == 0
            }

        if self.sensors["extended"]["type"]:
            name = self.sensors["extended"]["name"]
            self.outputs[name] = {
                "type": "signal",
                "value": self.position == 1
            }

    def get_visual_state(self):
            return self.position
    
    def get_state(self):
        state = super().get_state()
        state["position"] = self.position
        return state

    def set_state(self, state):
        super().set_state(state)
        self.position = state.get("position", self.position)

class OrValve(Node):
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id=node_id, node_type="or_valve", **kwargs)

        # Anchors pneumáticos
        self.add_anchor("X")
        self.add_anchor("Y")
        self.add_anchor("A")

        # Estado interno (shuttle com memória)
        self.active_input: str = "X"  # estado inicial

    def update(self, outputs=None):
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
    

    def get_state(self):
        state = super().get_state()
        state["active_input"] = self.active_input
        return state

    def set_state(self, state):
        super().set_state(state)
        self.active_input = state.get("active_input", self.active_input)
    


