# graphics/items/anchor.py
from PyQt6.QtCore import QPointF

class Anchor:
    def __init__(self, name: str, pos: QPointF, radius: float = 12):
        self.name = name
        self.pos = pos          # coordenada LOCAL do componente
        self.radius = radius