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
        # Mesma base/tamanho da AndValve agora (250x165), ver or_valve.py.
        from circuit_generator.sprite_metrics import METRICS as m
        assert m.or_width == 250
        assert m.or_height == 165

    def test_or_valve_x_anchor(self):
        # X = entrada esquerda: borda esquerda do sprite, y = 90/165 da
        # altura -- mesma proporção da AndValve (o sprite da OrValve usa
        # agora a mesma base/tamanho dela, ver or_valve.py).
        from circuit_generator.sprite_metrics import METRICS as m
        x, y = m.anchor_local["OrValve"]["X"]
        assert x == 0.0
        assert abs(y - 165 * 90 / 165) < 0.001

    def test_or_valve_y_anchor(self):
        # Y = entrada direita: borda direita do sprite, mesma altura que X
        from circuit_generator.sprite_metrics import METRICS as m
        x, y = m.anchor_local["OrValve"]["Y"]
        assert abs(x - 250.0) < 0.001
        assert abs(y - 165 * 90 / 165) < 0.001

    def test_or_valve_a_anchor(self):
        # A = saída: topo do sprite, centralizado (x = 50% da largura,
        # mesma proporção da AndValve)
        from circuit_generator.sprite_metrics import METRICS as m
        x, y = m.anchor_local["OrValve"]["A"]
        assert abs(x - 125.0) < 0.001
        assert y == 0.0


class TestValve32WaysPilotAnchors:
    def test_valve_3_2_ways_has_pl_and_pr(self):
        from circuit_generator.sprite_metrics import METRICS as m
        anchors = m.anchor_local["Valve_3_2_Ways"]
        assert "PL" in anchors
        assert "PR" in anchors

    def test_pl_is_left_of_body_pr_is_right_of_body(self):
        from circuit_generator.sprite_metrics import METRICS as m
        anchors = m.anchor_local["Valve_3_2_Ways"]
        pl_x, _ = anchors["PL"]
        pr_x, _ = anchors["PR"]
        assert pl_x < 0
        assert pr_x > m.v32_width


class TestPilotSideOffsetX:
    def test_matches_body_visuals_state1_offset_in_source(self):
        from circuit_generator.sprite_metrics import METRICS as m
        assert m.pilot_side_offset_x["Valve_3_2_Ways"] == 147.0
        assert m.pilot_side_offset_x["Valve_4_2_Ways"] == 147.0
        assert m.pilot_side_offset_x["Valve_5_2_Ways"] == 222.0


class TestSigColPitch:
    def test_covers_worst_case_commutation_shift(self):
        # sig_col_pitch precisa ser >= limit_switch_w + v32_width +
        # spring_w + pilot_side_offset_x -- o pior caso de duas sigs
        # adjacentes onde a da esquerda está comutada (corpo inteiro
        # deslocado pra direita) e a da direita não.
        from circuit_generator.sprite_metrics import METRICS as m
        expected = int(m.limit_switch_w + m.v32_width + m.spring_w
                       + m.pilot_side_offset_x["Valve_3_2_Ways"])
        assert m.sig_col_pitch == expected

    def test_wider_than_the_generic_pilot_based_sig_spacing(self):
        # sig_spacing (usado por layout_engine.py) aproxima o atuador
        # direito com pilot_w (100px) -- mas a sig do cascata usa spring
        # (136px) do lado direito, um sprite mais largo. sig_col_pitch
        # precisa refletir a largura REAL do spring, não a aproximação.
        from circuit_generator.sprite_metrics import METRICS as m
        assert m.spring_w > m.pilot_w
        assert m.sig_col_pitch > m.sig_spacing


class TestAnchorLocalForRouting:
    def test_pr_always_gets_the_commutation_margin(self):
        # Sempre, incondicionalmente -- não depende de default_side, já
        # que o deslocamento de comutação só empurra PR pra direita, nunca
        # pra esquerda, então base+offset é o pior caso em qualquer estado.
        from circuit_generator.sprite_metrics import anchor_local_for_routing, METRICS as m
        for node_type in ("Valve_3_2_Ways", "Valve_4_2_Ways", "Valve_5_2_Ways"):
            base_pr = m.anchor_local[node_type]["PR"]
            expected = (base_pr[0] + m.pilot_side_offset_x[node_type], base_pr[1])
            assert anchor_local_for_routing(node_type, "PR") == expected

    def test_pl_unchanged(self):
        from circuit_generator.sprite_metrics import anchor_local_for_routing, METRICS as m
        for node_type in ("Valve_3_2_Ways", "Valve_4_2_Ways", "Valve_5_2_Ways"):
            assert anchor_local_for_routing(node_type, "PL") == m.anchor_local[node_type]["PL"]

    def test_other_anchors_unchanged(self):
        from circuit_generator.sprite_metrics import anchor_local_for_routing, METRICS as m
        assert anchor_local_for_routing("Valve_4_2_Ways", "A") == m.anchor_local["Valve_4_2_Ways"]["A"]
        # Valve_3_2_Ways.P NAO fica inalterado -- ver test_p_gets_the_commutation_margin_only_for_valve_3_2_ways
        # abaixo. Valve_4_2_Ways.P/Valve_5_2_Ways.P continuam inalterados: nesta base de código
        # nenhuma delas jamais tem seu P alimentado por uma PressureLine (v42.P/mc.P vêm de um
        # Exhaust/PressureSource dedicado -- ver circuit_generator/methods/cascade.py), então o
        # deslocamento de comutação nunca é relevante ali.
        assert anchor_local_for_routing("Valve_4_2_Ways", "P") == m.anchor_local["Valve_4_2_Ways"]["P"]
        assert anchor_local_for_routing("Valve_5_2_Ways", "P") == m.anchor_local["Valve_5_2_Ways"]["P"]

    def test_p_gets_the_commutation_margin_only_for_valve_3_2_ways(self):
        # As válvulas de sinalização (Valve_3_2_Ways) que confirmam o
        # acionamento de uma 5/2 (cascata) ou de um pilot de 4/2 (ambos os
        # métodos) têm seu P alimentado direto por uma PressureLine -- o
        # mesmo mecanismo de deslocamento de comutação (BODY_VISUALS[1],
        # +147px) que já empurra PR pra direita também empurra P (calculado
        # como fração fixa de self.width, sem compensar o offset visual do
        # sprite) -- ver graphics/items/base/nodes/directional_valve/
        # valve_3_2_ways.py. Mesmo pior-caso incondicional já usado pra PR:
        # comutar só empurra pra direita, nunca pra esquerda.
        from circuit_generator.sprite_metrics import anchor_local_for_routing, METRICS as m
        base_p = m.anchor_local["Valve_3_2_Ways"]["P"]
        expected = (base_p[0] + m.pilot_side_offset_x["Valve_3_2_Ways"], base_p[1])
        assert anchor_local_for_routing("Valve_3_2_Ways", "P") == expected

    def test_unknown_anchor_returns_none(self):
        from circuit_generator.sprite_metrics import anchor_local_for_routing
        assert anchor_local_for_routing("Valve_4_2_Ways", "NOPE") is None
