from dataclasses import dataclass
from typing import Type

@dataclass(frozen=True)
class NodeDescriptor:
    cls: Type
    domain: str