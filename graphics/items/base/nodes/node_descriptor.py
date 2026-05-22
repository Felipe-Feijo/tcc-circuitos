"""Descritor imutável de um tipo de nó disponível na paleta."""

from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class PaletteMeta:
    """Metadados de paleta declarados diretamente na classe do nó.

    Retornado pelo classmethod ``palette_meta()`` de cada NodeItem concreto.
    Classes base (abstratas) retornam ``None`` — não aparecem na paleta.

    Attributes:
        domains: Lista de domínios em que o nó deve aparecer
                 (ex: ["pneumatic", "hydraulic"]).
        sprite:  Caminho para a imagem usada no ícone da paleta.
        name:    Nome exibido na paleta. Se None, usa ``cls.__name__``.
                 A ordem dentro de cada seção é sempre alfabética por ``name``.
    """
    domains: tuple[str, ...]
    sprite: str
    name: str | None = None
