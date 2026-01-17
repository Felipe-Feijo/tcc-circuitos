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


class Node:
    def __init__(self, node_id, node_type):
        self.id = node_id
        self.type = node_type
        self.anchors = {}

    def add_anchor(self, name):
        self.anchors[name] = Anchor(name, self)

    def get_anchor(self, name):
            return self.anchors[name]

    @classmethod
    def from_node_item(cls, item):
        node = cls(item.id, item.node_type)
        for a in item.anchors:
            node.add_anchor(a.name)
        return node