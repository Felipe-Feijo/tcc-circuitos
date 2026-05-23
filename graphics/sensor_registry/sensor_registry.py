"""Registro centralizado de sensores e atuadores da cena gráfica."""

from contextlib import contextmanager
from PyQt6.QtCore import QObject, pyqtSignal
from dataclasses import dataclass


@dataclass
class SensorInfo:
    """Metadados de um sensor registrado.

    Attributes:
        name: Nome único do sensor (ex: "A1", "B_ret").
        sensor_type: Tipo do sensor (ex: "reed", "proximity", "coil").
        owner: NodeItem proprietário do sensor.
    """
    name: str
    sensor_type: str
    owner: object


class SensorRegistry(QObject):
    """Mapeia nomes de sensores a seus proprietários e emite sinais de atualização.

    Usado pela UI de simulação para listar sensores disponíveis e pelo
    CircuitGenerator para garantir nomes únicos entre cilindros e bobinas.

    Durante o carregamento de arquivo (contexto loading()), os sinais são
    suprimidos para evitar atualizações parciais da UI.

    Signals:
        sensor_added(name, info): Emitido ao registrar um sensor.
        sensor_removed(name): Emitido ao remover um sensor.
        sensor_renamed(old_name, new_name, info): Emitido ao renomear.
    """

    sensor_added   = pyqtSignal(str, object)
    sensor_removed = pyqtSignal(str)
    sensor_renamed = pyqtSignal(str, str, object)

    def __init__(self):
        super().__init__()
        self._map: dict[str, SensorInfo] = {}
        self._load_depth = 0

    def register(self, name: str, sensor_type: str, node) -> bool:
        """Registra um sensor se o nome ainda não estiver em uso.

        Returns:
            True se registrado com sucesso, False se o nome já existia.
        """
        if name in self._map:
            return False

        info = SensorInfo(name, sensor_type, node)
        self._map[name] = info

        if not self.is_loading:
            self.sensor_added.emit(name, info)

        return True

    def unregister(self, name: str) -> None:
        """Remove um sensor do registro pelo nome."""
        if name in self._map:
            self._map.pop(name)
            if not self.is_loading:
                self.sensor_removed.emit(name)

    def rename(self, old_name: str, new_name: str, node) -> bool:
        """Renomeia um sensor existente.

        Returns:
            True se renomeado com sucesso, False se old_name não existe
            ou new_name já está em uso.
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
        """Retorna os nomes registrados, opcionalmente filtrados por tipo."""
        if sensor_type is None:
            return list(self._map.keys())

        return [
            name for name, info in self._map.items()
            if info.sensor_type == sensor_type
        ]

    def exists(self, name: str) -> bool:
        """Retorna True se o nome já está registrado."""
        return name in self._map

    def get(self, name: str) -> SensorInfo | None:
        """Retorna o SensorInfo pelo nome, ou None se não encontrado."""
        return self._map.get(name)

    def next_available_name(self, prefix: str = "A") -> str:
        """Retorna o próximo nome disponível com o prefixo dado (ex: A1, A2, ...)."""
        i = 1
        while f"{prefix}{i}" in self._map:
            i += 1
        return f"{prefix}{i}"

    @contextmanager
    def loading(self):
        """Contexto que suprime emissão de sinais durante carregamento em lote."""
        self._load_depth += 1
        try:
            yield
        finally:
            self._load_depth -= 1

    @property
    def is_loading(self) -> bool:
        """True se dentro de um contexto loading() ativo."""
        return self._load_depth > 0
