# graphics/items/anchor.py
from PyQt6.QtCore import QPointF
from graphics.items.base.nodes.node_item import NodeItem

class AnchorItem:
    def __init__(self, name: str, pos: QPointF, radius: float = 12, node: "NodeItem" = None):
        self.name = name
        self.id = name
        self.pos = pos         
        self.radius = radius
        self.node = node