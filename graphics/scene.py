"""Cena gráfica principal do editor de diagramas."""

from PyQt6.QtWidgets import QGraphicsScene

from graphics.sensor_registry.sensor_registry import SensorRegistry
from graphics.items.base.connections.connection_item import ConnectionItem


class GraphicsScene(QGraphicsScene):
    """Subclasse de QGraphicsScene que gerencia os itens do diagrama e o SensorRegistry.

    Responsabilidades adicionais em relação à classe base:
    - Manter o SensorRegistry compartilhado entre todos os itens da cena.
    - Desselecionar waypoints de conexão ao clicar em área vazia.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sensor_registry = SensorRegistry()

    def mousePressEvent(self, event):
        """Deseleciona waypoints ao clicar fora de uma ConnectionItem.

        Garante o comportamento esperado de "clicar em área vazia desmarca
        o waypoint selecionado", sem interferir com a seleção de itens normais.
        """
        hit_items = self.items(event.scenePos())
        if not any(isinstance(i, ConnectionItem) for i in hit_items):
            for item in self.items():
                if isinstance(item, ConnectionItem) and item._selected_wp is not None:
                    item._selected_wp = None
                    item.update()
        super().mousePressEvent(event)
