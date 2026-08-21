"""Centralized registry of the graphics scene's sensors and actuators."""

from contextlib import contextmanager
from PyQt6.QtCore import QObject, pyqtSignal
from dataclasses import dataclass


@dataclass
class SensorInfo:
    """Metadata for a registered sensor.

    Attributes:
        name: The sensor's unique name (e.g. "A1", "B_ret").
        sensor_type: The sensor's type (e.g. "reed", "proximity", "coil").
        owner: The sensor's owning NodeItem.
    """
    name: str
    sensor_type: str
    owner: object


class SensorRegistry(QObject):
    """Maps sensor names to their owners and emits update signals.

    Used by the simulation UI to list available sensors and by
    CircuitGenerator to guarantee unique names across cylinders and coils.

    During file loading (the loading() context), signals are suppressed
    to avoid partial UI updates.

    Signals:
        sensor_added(name, info): Emitted when a sensor is registered.
        sensor_removed(name): Emitted when a sensor is removed.
        sensor_renamed(old_name, new_name, info): Emitted on rename.
    """

    sensor_added   = pyqtSignal(str, object)
    sensor_removed = pyqtSignal(str)
    sensor_renamed = pyqtSignal(str, str, object)

    def __init__(self):
        super().__init__()
        self._map: dict[str, SensorInfo] = {}
        self._load_depth = 0

    def register(self, name: str, sensor_type: str, node) -> bool:
        """Registers a sensor if the name isn't already in use.

        Returns:
            True if registered successfully, False if the name already existed.
        """
        if name in self._map:
            return False

        info = SensorInfo(name, sensor_type, node)
        self._map[name] = info

        if not self.is_loading:
            self.sensor_added.emit(name, info)

        return True

    def unregister(self, name: str) -> None:
        """Removes a sensor from the registry by name."""
        if name in self._map:
            self._map.pop(name)
            if not self.is_loading:
                self.sensor_removed.emit(name)

    def rename(self, old_name: str, new_name: str, node) -> bool:
        """Renames an existing sensor.

        Returns:
            True if renamed successfully, False if old_name doesn't
            exist or new_name is already in use.
        """
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

    def list_names(self, sensor_type: str | None = None) -> list[str]:
        """Returns the registered names, optionally filtered by type."""
        if sensor_type is None:
            return list(self._map.keys())

        return [
            name for name, info in self._map.items()
            if info.sensor_type == sensor_type
        ]

    def exists(self, name: str) -> bool:
        """Returns True if the name is already registered."""
        return name in self._map

    def get(self, name: str) -> SensorInfo | None:
        """Returns the SensorInfo by name, or None if not found."""
        return self._map.get(name)

    def next_available_name(self, prefix: str = "A") -> str:
        """Returns the next available name with the given prefix (e.g. A1, A2, ...)."""
        i = 1
        while f"{prefix}{i}" in self._map:
            i += 1
        return f"{prefix}{i}"

    @contextmanager
    def loading(self):
        """Context that suppresses signal emission during batch loading."""
        self._load_depth += 1
        try:
            yield
        finally:
            self._load_depth -= 1

    @property
    def is_loading(self) -> bool:
        """True if inside an active loading() context."""
        return self._load_depth > 0
