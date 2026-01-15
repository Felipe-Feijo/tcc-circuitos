# domain/components.py

from __future__ import annotations
from typing import Dict, List


class Anchor:
    def __init__(self, name: str, component: "Component"):
        self.component = component
        self.name = name
        self.id = (component.id, name)
        self.connections: List["Connection"] = []

    def connect(self, connection: "Connection"):
        if connection not in self.connections:
            self.connections.append(connection)


class Component:
    def __init__(self, component_id, comp_type):
        self.id = component_id
        self.type = comp_type
        self.anchors = {}

    def add_anchor(self, name):
        self.anchors[name] = Anchor(name, self)

    def get_anchor(self, name):
            return self.anchors[name]

    @classmethod
    def from_component_item(cls, item):
        comp = cls(item.id, item.component_type)
        for a in item.anchors:
            comp.add_anchor(a.name)
        return comp