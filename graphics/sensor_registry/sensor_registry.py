from PyQt6.QtCore import QObject, pyqtSignal
class SensorRegistry(QObject):

    sensor_added = pyqtSignal(str, object)
    sensor_removed = pyqtSignal(str)
    sensor_renamed = pyqtSignal(str, str, object)

    def __init__(self):
        super().__init__()
        self._map = {}  # name -> owner_node

    def register(self, name: str, node):
        if name in self._map:
            return False

        self._map[name] = node
        self.sensor_added.emit(name, node)
        return True

    def unregister(self, name: str):
        if name in self._map:
            self._map.pop(name)
            self.sensor_removed.emit(name)

    def rename(self, old_name: str, new_name: str, node):
        if old_name not in self._map:
            return False

        if new_name in self._map:
            return False

        self._map.pop(old_name)
        self._map[new_name] = node

        self.sensor_renamed.emit(old_name, new_name, node)
        return True

    def list_names(self):
        return list(self._map.keys())

    def exists(self, name: str):
        return name in self._map
    
    # 🔹 novo
    def next_available_name(self, prefix="A"):
        i = 1
        while f"{prefix}{i}" in self._map:
            i += 1
        return f"{prefix}{i}"