"""Immutable descriptor for a node type available in the palette."""

from dataclasses import dataclass, field
from typing import Type


@dataclass(frozen=True)
class NodeDescriptor:
    """Metadata for a node type, used by the palette and ADD mode.

    Immutable (frozen=True) -- never changed after creation.

    Attributes:
        cls: The concrete NodeItem class to instantiate.
        domain: The node's domain ("pneumatic", "electric" or "hydraulic").
    """
    cls: Type
    domain: str


@dataclass(frozen=True)
class PaletteMeta:
    """Palette metadata declared directly on the node's class.

    Returned by each concrete NodeItem's ``palette_meta()`` classmethod.
    Base (abstract) classes return ``None`` -- they don't appear in the palette.

    Attributes:
        domains: List of domains the node should appear in
                 (e.g. ["pneumatic", "hydraulic"]).
        sprite:  Path to the image used for the palette icon.
        name:    Name shown in the palette. If None, uses ``cls.__name__``.
                 Order within each section is always alphabetical by ``name``.
    """
    domains: tuple[str, ...]
    sprite: str
    name: str | None = None
