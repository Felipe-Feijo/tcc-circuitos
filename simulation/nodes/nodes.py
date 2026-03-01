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
        self.pressure_var: str | None = None  # nome da variável P_* no sistema, preenchido pela engine
        self.fault = False

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
        anchors_state = {}
        for name, anchor in self.anchors.items():
            anchor_data = {"state": anchor.state}
            if anchor.domain == "hydraulic":
                anchor_data["pressure"] = anchor.pressure
                anchor_data["flow"]     = anchor.flow
                anchor_data["fault"]    = getattr(anchor, "fault", False)
            anchors_state[name] = anchor_data

        return {"anchors": anchors_state}

    def set_state(self, state: dict):
        for name, anchor_data in state.get("anchors", {}).items():
            anchor = self.anchors.get(name)
            if not anchor:
                continue
            anchor.state = anchor_data.get("state", anchor.state)
            if anchor.domain == "hydraulic":
                anchor.pressure = anchor_data.get("pressure", anchor.pressure)
                anchor.flow     = anchor_data.get("flow", anchor.flow)
                anchor.fault    = anchor_data.get("fault", False)

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

    def post_step_update(self, dt):
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
    


