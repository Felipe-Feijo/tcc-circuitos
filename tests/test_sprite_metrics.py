"""Testes de regressão e cobertura para sprite_metrics.py — a mudança do
parser de frações de anchor (bool y_is_height -> float y_ratio) não pode
alterar nenhum valor já correto dos componentes existentes, e precisa
adicionar a entrada de OrValve que não existe hoje.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestExistingAnchorsUnchanged:
    """Valores capturados rodando o código atual (antes desta mudança)
    contra os PNGs reais do repositório — travam a regressão."""

    def test_valve_4_2_ways_pl(self):
        from circuit_generator.sprite_metrics import METRICS as m
        x, y = m.anchor_local["Valve_4_2_Ways"]["PL"]
        assert x == -100
        assert abs(y - 111.996) < 0.001

    def test_valve_4_2_ways_pr(self):
        from circuit_generator.sprite_metrics import METRICS as m
        x, y = m.anchor_local["Valve_4_2_Ways"]["PR"]
        assert x == 400
        assert abs(y - 111.996) < 0.001

    def test_valve_4_2_ways_a(self):
        from circuit_generator.sprite_metrics import METRICS as m
        x, y = m.anchor_local["Valve_4_2_Ways"]["A"]
        assert abs(x - 191.0) < 0.001
        assert y == 0.0

    def test_valve_3_2_ways_a(self):
        from circuit_generator.sprite_metrics import METRICS as m
        x, y = m.anchor_local["Valve_3_2_Ways"]["A"]
        assert abs(x - 254.0) < 0.001
        assert y == 0.0

    def test_double_acting_cylinder_a(self):
        from circuit_generator.sprite_metrics import METRICS as m
        x, y = m.anchor_local["DoubleActingCylinder"]["A"]
        assert abs(x - 18.036217303822937) < 0.0001
        assert y == 193

    def test_double_acting_cylinder_b(self):
        from circuit_generator.sprite_metrics import METRICS as m
        x, y = m.anchor_local["DoubleActingCylinder"]["B"]
        assert abs(x - 408.82092555331997) < 0.0001
        assert y == 193


class TestOrValveAnchors:
    def test_or_valve_present(self):
        from circuit_generator.sprite_metrics import METRICS as m
        assert "OrValve" in m.anchor_local

    def test_or_valve_sprite_size(self):
        from circuit_generator.sprite_metrics import METRICS as m
        assert m.or_width == 130
        assert m.or_height == 71

    def test_or_valve_x_anchor(self):
        # X = entrada esquerda: borda esquerda do sprite, y = 54.29% da altura
        from circuit_generator.sprite_metrics import METRICS as m
        x, y = m.anchor_local["OrValve"]["X"]
        assert x == 0.0
        assert abs(y - 38.5459) < 0.001

    def test_or_valve_y_anchor(self):
        # Y = entrada direita: borda direita do sprite, mesma altura que X
        from circuit_generator.sprite_metrics import METRICS as m
        x, y = m.anchor_local["OrValve"]["Y"]
        assert abs(x - 130.0) < 0.001
        assert abs(y - 38.5459) < 0.001

    def test_or_valve_a_anchor(self):
        # A = saída: topo do sprite, x = 50.39% da largura
        from circuit_generator.sprite_metrics import METRICS as m
        x, y = m.anchor_local["OrValve"]["A"]
        assert abs(x - 65.507) < 0.001
        assert y == 0.0
