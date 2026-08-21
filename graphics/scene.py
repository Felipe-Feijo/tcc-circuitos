"""Main graphics scene of the diagram editor."""

from PyQt6.QtWidgets import QGraphicsScene

from graphics.sensor_registry.sensor_registry import SensorRegistry
from graphics.items.base.connections.connection_item import ConnectionItem


class GraphicsScene(QGraphicsScene):
    """QGraphicsScene subclass that manages the diagram items and the SensorRegistry.

    Additional responsibilities beyond the base class:
    - Keep the SensorRegistry shared across all scene items.
    - Deselect connection waypoints when clicking on empty area.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sensor_registry = SensorRegistry()

    def mousePressEvent(self, event):
        """Deselects waypoints when clicking outside a ConnectionItem.

        Ensures the expected behavior of "clicking empty area deselects
        the selected waypoint", without interfering with normal item selection.
        """
        hit_items = self.items(event.scenePos())
        if not any(isinstance(i, ConnectionItem) for i in hit_items):
            for item in self.items():
                if isinstance(item, ConnectionItem) and item._selected_wp is not None:
                    item._selected_wp = None
                    item.update()
        super().mousePressEvent(event)
