from PyQt6.QtWidgets import QGraphicsScene

from graphics.sensor_registry.sensor_registry import SensorRegistry
from graphics.items.base.connections.connection_item import ConnectionItem

class GraphicsScene(QGraphicsScene):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sensor_registry = SensorRegistry()

    def mousePressEvent(self, event):
        # Clear any selected waypoint when the user clicks anywhere that is
        # not an item (or not a connection item).  This gives the expected
        # "click away to deselect" behaviour for waypoints.
        hit_items = self.items(event.scenePos())
        if not any(isinstance(i, ConnectionItem) for i in hit_items):
            for item in self.items():
                if isinstance(item, ConnectionItem) and item._selected_wp is not None:
                    item._selected_wp = None
                    item.update()
        super().mousePressEvent(event)