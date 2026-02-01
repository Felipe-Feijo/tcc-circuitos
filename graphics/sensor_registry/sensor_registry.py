class SensorRegistry:
    def __init__(self):
        self._map = {}  # name -> owner_node

    def register(self, name: str, node):
        if name in self._map:
            return False   # nome já existe
        self._map[name] = node
        return True

    def unregister(self, name: str):
        self._map.pop(name, None)

    def rename(self, old_name: str, new_name: str, node):
        if new_name in self._map:
            return False

        self.unregister(old_name)
        self._map[new_name] = node
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