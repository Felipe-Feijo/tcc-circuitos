from PyQt6.QtWidgets import QGraphicsScene

from graphics.sensor_registry.sensor_registry import SensorRegistry

class GraphicsScene(QGraphicsScene):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.sensor_registry = SensorRegistry()