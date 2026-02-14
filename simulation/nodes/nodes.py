# domain/components.py

from __future__ import annotations
from typing import Dict, List


class Anchor:
    def __init__(self, name: str, node: "Node", domain: str):
        self.node = node
        self.name = name
        self.domain = domain
        self.id = (node.id, name)
        self.connections: list["Connection"] = []

        # novo: estado genérico do domínio
        self.state: bool = False

        # ainda útil para driver/solenoides, bombas etc.
        self.is_driver: bool = False

        # atributos específicos por domínio (opcional)
        # elétrica
        self.type: str | None = None  # "source", "ground", "regular"
        # hidráulica
        self.pressure: float = 0.0    # opcional, se quiser modelar pressão real
        self.flow: float = 0.0        # opcional, se quiser modelar vazão

    def connect(self, connection: "Connection"):
        if connection not in self.connections:
            self.connections.append(connection)


class Node:
    def __init__(self, node_id, node_type, **kwargs):
        self.id = node_id
        self.type = node_type
        self.anchors = {}

        self.domain = kwargs.pop("domain", None)
        self.properties = kwargs.pop("properties", {}) or {}

    def add_anchor(self, name, domain) -> Anchor:
        anchor = Anchor(name, self, domain)
        self.anchors[name] = anchor
        return anchor

    def get_anchor(self, name):
        return self.anchors[name]
    
    def get_state(self) -> dict:
        return {
            "anchors": {
                name: anchor.state
                for name, anchor in self.anchors.items()
            }
        }

    def set_state(self, state: dict):
        anchor_states = state.get("anchors", {})
        for name, state in anchor_states.items():
            if name in self.anchors:
                self.anchors[name].state = state

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

    def update(self, outputs=None):
        self.get_anchor("P").state = True
        self.get_anchor("P").is_driver = True

class Exhaust(Node):
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id=node_id, node_type="exhaust", **kwargs)

    def update(self, outputs=None):
        self.get_anchor("R").state = False
        self.get_anchor("R").is_driver = True


    
class SingleActingCylinder(Node):
    def __init__(self, node_id, **kwargs):
        super().__init__(node_id, "single_acting_cylinder", **kwargs)

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
        self.position = 1 if self.anchors["A"].state else 0

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

        # Estado interno (shuttle com memória)
        self.active_input: str = "X"  # estado inicial

    def update(self, outputs=None):
        x = self.anchors["X"].state
        y = self.anchors["Y"].state

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
    


