# graphics/items/anchor.py
from PyQt6.QtCore import QPointF

class AnchorItem:
    def __init__(self, name: str, pos: QPointF, radius: float = 12, component: "ComponentItem" = None):
        self.name = name
        self.id = name
        self.pos = pos          # coordenada LOCAL do componente
        self.radius = radius
        self.component = component