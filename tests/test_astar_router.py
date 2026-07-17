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


class TestCommutationShiftInBlockingRect:
    """Regressão real (achada testando a UI real): build_grid() bloqueava
    o retângulo de colisão na posição LÓGICA (não-deslocada) de uma
    válvula direcional -- quando ela está no estado comutado
    (default_side == "left" -> body_state=1), o sprite de verdade
    (BODY_VISUALS[1]["offset"]) renderiza deslocado pra direita, mas o
    retângulo de bloqueio não acompanhava. Um fio podia entrar "por
    dentro" do corpo real (achado com sig.A -> mem.PR cruzando uma
    memória comutada), porque o A* achava aquele trecho livre baseado no
    retângulo desatualizado."""

    def _valve_node(self, node_id: str, x: float, y: float, node_type: str, default_side: str) -> dict:
        return {
            "id": node_id, "type": node_type,
            "position": {"x": x, "y": y},
            "properties": {"default_side": default_side},
        }

    def test_commuted_valve_blocks_the_shifted_position(self):
        import math
        from circuit_generator.astar_router import build_grid

        node = self._valve_node("mem", 1000, 1000, "Valve_5_2_Ways", "left")  # comutada
        grid = build_grid([node])
        shift = M.pilot_side_offset_x["Valve_5_2_Ways"]
        # perto da borda direita do corpo deslocado -- fora do alcance do
        # corpo NAO deslocado + margem (MH=80), so bloqueia se o
        # deslocamento de comutacao for aplicado de verdade
        target_x = 1000 + shift + M.v52_width - 10
        cx, cy = grid.px_to_cell(target_x, 1000 + M.v52_height / 2)
        assert grid.cost(cx, cy) == math.inf

    def test_non_commuted_valve_does_not_block_the_shifted_position(self):
        import math
        from circuit_generator.astar_router import build_grid

        node = self._valve_node("mem", 1000, 1000, "Valve_5_2_Ways", "right")  # nao comutada
        grid = build_grid([node])
        shift = M.pilot_side_offset_x["Valve_5_2_Ways"]
        # mesma posicao do teste acima -- sem comutacao, deve estar livre
        target_x = 1000 + shift + M.v52_width - 10
        cx, cy = grid.px_to_cell(target_x, 1000 + M.v52_height / 2)
        assert grid.cost(cx, cy) != math.inf


class TestOrValveVerticalMargin:
    """Feedback direto testando a UI real: OrValve caía no ramo genérico
    de build_grid() (bloqueio exato do sprite, sem margem nenhuma) -- um
    fio podia passar rente por cima/embaixo do corpo. Adicionada uma
    margem vertical pequena (MV_OR) só pra esse tipo -- X/Y (esquerda/
    direita) já tinham folga própria via _find_free_exit, não precisam
    de margem horizontal."""

    def test_blocks_a_small_margin_above_and_below(self):
        import math
        from circuit_generator.astar_router import build_grid

        node = {"id": "or1", "type": "OrValve", "position": {"x": 1000, "y": 1000},
                "properties": {}}
        grid = build_grid([node])
        mid_x = 1000 + M.or_width / 2
        above = grid.px_to_cell(mid_x, 1000 - 10)
        below = grid.px_to_cell(mid_x, 1000 + M.or_height + 10)
        assert grid.cost(*above) == math.inf
        assert grid.cost(*below) == math.inf

    def test_margin_does_not_extend_too_far(self):
        import math
        from circuit_generator.astar_router import build_grid

        node = {"id": "or1", "type": "OrValve", "position": {"x": 1000, "y": 1000},
                "properties": {}}
        grid = build_grid([node])
        # +CELL de folga além da margem, pra não cair na mesma célula de
        # 20px que ainda está dentro do bloqueio por arredondamento.
        mid_x = 1000 + M.or_width / 2
        above = grid.px_to_cell(mid_x, 1000 - 20 - 20)
        below = grid.px_to_cell(mid_x, 1000 + M.or_height + 20 + 20)
        assert grid.cost(*above) != math.inf
        assert grid.cost(*below) != math.inf
