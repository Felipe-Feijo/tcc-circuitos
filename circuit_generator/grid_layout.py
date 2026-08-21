"""Generic grid-based positioning engine.

One single Grid instance per generated circuit: each row has a fixed
cell width/height and an explicit Y position, and each cell is
addressed by a named column (column_key) -- any hashable value,
typically a "branch" identifier (e.g. a cylinder letter). The same
column_key used across different rows gets, in each row, that row's
arrival index -- no guarantee of pixel alignment between rows with
different widths (a design decision, see spec).
"""

from dataclasses import dataclass, field
from typing import Hashable, Iterable


@dataclass
class _Row:
    cell_width: float
    cell_height: float
    y: float
    x_origin: float
    column_index: dict = field(default_factory=dict)


class Grid:
    def __init__(self) -> None:
        self._rows: dict[str, _Row] = {}
        self._positions: dict[str, tuple[float, float]] = {}
        self._occupant: dict[tuple[str, Hashable], str] = {}
        self._node_cell: dict[str, tuple[str, Hashable]] = {}

    def add_row(self, row_id: str, cell_width: float, cell_height: float,
                y: float, x_origin: float = 0.0) -> None:
        """Registers a row. Raises ValueError if row_id already exists."""
        if row_id in self._rows:
            raise ValueError(f"Row {row_id!r} already registered")
        self._rows[row_id] = _Row(cell_width, cell_height, y, x_origin)

    def place(self, row_id: str, column_key: Hashable, node_id: str) -> tuple[float, float]:
        """
        Allocates node_id in cell (row_id, column_key) and returns its
        (x, y) position. If column_key was already used in this row by
        ANOTHER node_id, or if node_id was already allocated in another
        cell, raises ValueError (one cell per component, one component
        per cell). Calling again with the SAME cell and the SAME node_id
        is idempotent (returns the same position). Raises KeyError if
        row_id wasn't registered via add_row.
        """
        row = self._rows[row_id]
        cell_key = (row_id, column_key)

        existing_occupant = self._occupant.get(cell_key)
        if existing_occupant is not None and existing_occupant != node_id:
            raise ValueError(
                f"Cell ({row_id!r}, {column_key!r}) already occupied by "
                f"{existing_occupant!r}, can't allocate {node_id!r}"
            )

        existing_cell = self._node_cell.get(node_id)
        if existing_cell is not None and existing_cell != cell_key:
            raise ValueError(
                f"{node_id!r} was already allocated at {existing_cell!r}, "
                f"can't be reallocated to {cell_key!r}"
            )

        if column_key not in row.column_index:
            row.column_index[column_key] = len(row.column_index)
        self._occupant[cell_key] = node_id
        self._node_cell[node_id] = cell_key

        col_idx = row.column_index[column_key]
        x = row.x_origin + col_idx * row.cell_width
        y = row.y
        self._positions[node_id] = (x, y)
        return (x, y)

    def position_of(self, node_id: str) -> tuple[float, float] | None:
        """Returns the position already assigned to node_id, or None if
        not yet positioned."""
        return self._positions.get(node_id)

    def occupied_x_range(self, exclude_rows: Iterable[str] = ()) -> tuple[float, float] | None:
        """(min_x, max_x) across positions already assigned to nodes,
        excluding those in exclude_rows' rows. None if no node was
        positioned outside them."""
        exclude = set(exclude_rows)
        xs = [x for node_id, (x, _y) in self._positions.items()
              if self._node_cell[node_id][0] not in exclude]
        return (min(xs), max(xs)) if xs else None
