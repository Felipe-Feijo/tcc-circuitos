"""Defines the interaction modes of the diagram editor."""

from enum import Enum


class EditorMode(Enum):
    """Interaction modes available in the editor.

    Attributes:
        SELECT:   Selecting and moving items.
        ADD:      Placing a new node from the palette.
        CONNECT:  Creating a connection between two anchors.
        SIMULATE: Running the simulation; editing disabled.
    """

    SELECT = None
    ADD = "add"
    CONNECT = "connect"
    SIMULATE = "simulate"
