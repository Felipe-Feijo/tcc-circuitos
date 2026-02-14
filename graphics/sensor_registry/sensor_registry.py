from contextlib import contextmanager
from PyQt6.QtCore import QObject, pyqtSignal
from dataclasses import dataclass

@dataclass
class SensorInfo:
    name: str
    sensor_type: str
    owner: object


class SensorRegistry(QObject):

    sensor_added = pyqtSignal(str, object)
    sensor_removed = pyqtSignal(str)
    sensor_renamed = pyqtSignal(str, str, object)

    def __init__(self):
        super().__init__()
        self._map: dict[str, SensorInfo] = {}
        self._load_depth = 0

    def register(self, name: str, sensor_type: str, node):
        if name in self._map:
            return False

        info = SensorInfo(name, sensor_type, node)
        self._map[name] = info

        if not self.is_loading:
            self.sensor_added.emit(name, info)

        return True

    def unregister(self, name: str):
        if name in self._map:
            self._map.pop(name)
            if not self.is_loading:
                self.sensor_removed.emit(name)

    def rename(self, old_name: str, new_name: str, node):
        if old_name not in self._map:
            return False

        if new_name in self._map:
            return False

        info = self._map.pop(old_name)
        info.name = new_name
        self._map[new_name] = info
        
        if not self.is_loading:
            self.sensor_renamed.emit(old_name, new_name, info)

        return True

    def list_names(self, sensor_type=None):
        if sensor_type is None:
            return list(self._map.keys())

        return [
            name for name, info in self._map.items()
            if info.sensor_type == sensor_type
        ]

    def exists(self, name: str):
        return name in self._map

    def get(self, name: str):
        return self._map.get(name)

    def next_available_name(self, prefix="A"):
        i = 1
        while f"{prefix}{i}" in self._map:
            i += 1
        return f"{prefix}{i}"

    @contextmanager
    def loading(self):
        self._load_depth += 1
        try:
            yield
        finally:
            self._load_depth -= 1

    @property
    def is_loading(self):
        return self._load_depth > 0