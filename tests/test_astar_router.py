"""Testes para circuit_generator/astar_router.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.astar_router import SPRITE_SIZES
from circuit_generator.sprite_metrics import METRICS as M


class TestSpriteSizesMatchMetrics:
    """SPRITE_SIZES bloqueia retângulos de colisão pro roteador A* -- tem que
    bater com as dimensões REAIS dos sprites (sprite_metrics.py, lidas do
    PNG). Um valor hardcoded desatualizado aqui infla o retângulo de
    bloqueio além do corpo real do sprite, e um anchor legitimamente
    posicionado logo além da borda de verdade (ex: PR de Valve_4_2_Ways,
    que fica pilot_w além do corpo) acaba caindo "dentro" desse bloqueio
    inflado -- forçando o roteador a escapar bem mais longe do que
    necessário e depois saltar de volta (bug encontrado com
    parse("A+A-B+B-"): SPRITE_SIZES tinha Valve_4_2_Ways=(447,180) contra
    os 300x180 reais, uma diferença de 147px -- exatamente o tamanho do
    salto final observado no fio do pilot PR)."""

    def test_valve_widths_match_sprite_metrics(self):
        assert SPRITE_SIZES["Valve_4_2_Ways"] == (M.v42_width, M.v42_height)
        assert SPRITE_SIZES["Valve_5_2_Ways"] == (M.v52_width, M.v52_height)
        assert SPRITE_SIZES["Valve_3_2_Ways"] == (M.v32_width, M.v32_height)

    def test_cylinder_size_matches_sprite_metrics(self):
        assert SPRITE_SIZES["DoubleActingCylinder"] == (M.cyl_width, M.cyl_height)

    def test_small_obstacle_sizes_match_sprite_metrics(self):
        assert SPRITE_SIZES["Exhaust"] == (M.exh_width, M.exh_height)
        assert SPRITE_SIZES["PressureSource"] == (M.ps_width, M.ps_height)

    def test_pressure_line_size_matches_sprite_metrics(self):
        assert SPRITE_SIZES["PressureLine"] == (M.pl_pix_w, M.pl_pix_h)
