"""Descritor imutável de um tipo de nó disponível na paleta."""

from dataclasses import dataclass
from typing import Type


@dataclass(frozen=True)
class NodeDescriptor:
    """Metadados de um tipo de nó para uso na paleta e no modo ADD.

    Imutável (frozen=True) — nunca alterado após criação.

    Attributes:
        cls: Classe concreta do NodeItem a ser instanciada.
        domain: Domínio do nó ("pneumatic", "electric" ou "hydraulic").
    """
    cls: Type
    domain: str
