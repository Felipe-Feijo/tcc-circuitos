"""Testes para o motor de grid genérico — ver
docs/superpowers/specs/2026-07-10-grid-layout-engine-core-design.md
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from circuit_generator.grid_layout import Grid


class TestAddRow:
    def test_duplicate_row_id_raises(self):
        grid = Grid()
        grid.add_row("cylinders", 500, 200, y=0)
        with pytest.raises(ValueError):
            grid.add_row("cylinders", 500, 200, y=100)

    def test_rows_registered_out_of_y_order_work_normally(self):
        grid = Grid()
        grid.add_row("below", 200, 100, y=50)
        grid.add_row("above", 200, 100, y=0)
        assert grid.place("below", "A", "node-below") == (0, 50)
        assert grid.place("above", "A", "node-above") == (0, 0)


class TestPlace:
    def test_place_on_unregistered_row_raises_keyerror(self):
        grid = Grid()
        with pytest.raises(KeyError):
            grid.place("nope", "A", "node-1")

    def test_first_column_key_gets_index_zero(self):
        grid = Grid()
        grid.add_row("row1", cell_width=500, cell_height=200, y=100, x_origin=1000)
        assert grid.place("row1", "A", "node-A") == (1000, 100)

    def test_second_column_key_gets_index_one(self):
        grid = Grid()
        grid.add_row("row1", cell_width=500, cell_height=200, y=100, x_origin=1000)
        grid.place("row1", "A", "node-A")
        assert grid.place("row1", "B", "node-B") == (1500, 100)

    def test_same_column_key_different_node_id_raises(self):
        grid = Grid()
        grid.add_row("row1", 500, 200, y=0)
        grid.place("row1", "A", "node-A")
        with pytest.raises(ValueError):
            grid.place("row1", "A", "node-other")

    def test_same_column_key_same_node_id_is_idempotent(self):
        grid = Grid()
        grid.add_row("row1", 500, 200, y=0)
        pos1 = grid.place("row1", "A", "node-A")
        pos2 = grid.place("row1", "A", "node-A")
        assert pos1 == pos2 == (0, 0)

    def test_same_column_key_different_rows_different_cell_widths_no_cross_alignment(self):
        grid = Grid()
        grid.add_row("wide", cell_width=600, cell_height=180, y=0)
        grid.add_row("narrow", cell_width=200, cell_height=100, y=500)
        # Coloca as MESMAS 3 chaves, na MESMA ordem, nas duas linhas -- "Z"
        # cai no índice 2 em ambas (mesma ordem de chegada), mas a posição
        # X final difere porque as larguras de célula são diferentes.
        for key, wide_id, narrow_id in [("X", "w0", "n0"), ("Y", "w1", "n1"), ("Z", "w2", "n2")]:
            grid.place("wide", key, wide_id)
            grid.place("narrow", key, narrow_id)
        assert grid.position_of("w2") == (1200, 0)
        assert grid.position_of("n2") == (400, 500)


class TestPositionOf:
    def test_unplaced_node_returns_none(self):
        grid = Grid()
        assert grid.position_of("nonexistent") is None

    def test_placed_node_returns_its_position(self):
        grid = Grid()
        grid.add_row("row1", 500, 200, y=0)
        grid.place("row1", "A", "node-A")
        assert grid.position_of("node-A") == (0, 0)
