"""Motor de posicionamento genérico baseado em grid.

Uma única instância de Grid por circuito gerado: cada linha (row) tem uma
largura/altura de célula fixa e uma posição Y explícita, e cada célula é
endereçada por uma coluna nomeada (column_key) — qualquer valor hashável,
tipicamente um identificador de "ramo" (ex: letra de cilindro). A mesma
column_key usada em linhas diferentes recebe, em cada linha, o índice de
chegada daquela linha — sem garantia de alinhamento de pixel entre linhas
de larguras diferentes (decisão de design, ver spec).
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
        """Registra uma linha. Lança ValueError se row_id já existe."""
        if row_id in self._rows:
            raise ValueError(f"Linha {row_id!r} já registrada")
        self._rows[row_id] = _Row(cell_width, cell_height, y, x_origin)

    def place(self, row_id: str, column_key: Hashable, node_id: str) -> tuple[float, float]:
        """
        Aloca node_id na célula (row_id, column_key) e devolve sua posição
        (x, y). Se column_key já foi usada nesta linha por OUTRO node_id, ou
        se node_id já foi alocado em outra célula, lança ValueError (uma
        célula por componente, um componente por célula). Chamar de novo com
        a MESMA célula e o MESMO node_id é idempotente (devolve a mesma
        posição). Lança KeyError se row_id não foi registrado via add_row.
        """
        row = self._rows[row_id]
        cell_key = (row_id, column_key)

        existing_occupant = self._occupant.get(cell_key)
        if existing_occupant is not None and existing_occupant != node_id:
            raise ValueError(
                f"Célula ({row_id!r}, {column_key!r}) já ocupada por "
                f"{existing_occupant!r}, não pode alocar {node_id!r}"
            )

        existing_cell = self._node_cell.get(node_id)
        if existing_cell is not None and existing_cell != cell_key:
            raise ValueError(
                f"{node_id!r} já foi alocado em {existing_cell!r}, não pode "
                f"ser realocado em {cell_key!r}"
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
        """Devolve a posição já atribuída a node_id, ou None se ainda não
        foi posicionado."""
        return self._positions.get(node_id)

    def occupied_x_range(self, exclude_rows: Iterable[str] = ()) -> tuple[float, float] | None:
        """(min_x, max_x) entre as posições já atribuídas a nós, excluindo
        os das linhas em exclude_rows. None se nenhum nó foi posicionado
        fora delas."""
        exclude = set(exclude_rows)
        xs = [x for node_id, (x, _y) in self._positions.items()
              if self._node_cell[node_id][0] not in exclude]
        return (min(xs), max(xs)) if xs else None
