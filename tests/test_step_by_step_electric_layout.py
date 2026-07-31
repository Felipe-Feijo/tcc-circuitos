"""Testes para circuit_generator/step_by_step_electric_layout.py — ver
docs/superpowers/specs/2026-07-30-step-by-step-electric-layout-design.md
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from circuit_generator.sequence_parser import parse
from circuit_generator.methods import step_by_step_electric as sbe
from circuit_generator import step_by_step_electric_layout as layout
from circuit_generator.sprite_metrics import METRICS as _M, anchor_local_for_routing


def _node(data, node_id):
    return next(n for n in data["nodes"] if n["id"] == node_id)


def _scene_xy(data, node_id, anchor_name):
    """Réplica da _scene_xy interna de step_by_step_electric_layout.apply()
    (não exposta -- é uma closure local) -- calcula a posição real de tela
    de um anchor, incluindo os casos especiais de VoltageSource/Ground
    (anchors "Xi" indexados na lista properties.anchors, não um offset
    fixo)."""
    n = _node(data, node_id)
    pos = n["position"]
    ntype = n["type"]
    if ntype == "VoltageSource" and anchor_name.startswith("X"):
        anchors = n["properties"]["anchors"]
        idx = anchors.index(anchor_name)
        return (pos["x"] + _M.vsource_pix_w + idx * _M.pl_spacing,
                pos["y"] + _M.vsource_pix_h * 69 / 100)
    if ntype == "Ground" and anchor_name.startswith("X"):
        anchors = n["properties"]["anchors"]
        idx = anchors.index(anchor_name)
        return (pos["x"] + _M.ground_pix_w * 0.5 + idx * _M.pl_spacing, pos["y"])
    local = anchor_local_for_routing(ntype, anchor_name)
    return (pos["x"] + local[0], pos["y"] + local[1]) if local else (pos["x"], pos["y"])


def _assert_connection_orthogonal(data, conn):
    """Uma conexão é válida se tem waypoints OU se source/target (+ todos os
    waypoints, se houver) formam uma cadeia de segmentos alinhados a um
    único eixo (X ou Y) por vez -- nunca diagonal."""
    s = conn["source"]
    t = conn["target"]
    spos = _scene_xy(data, s["node"], s["anchor"])
    tpos = _scene_xy(data, t["node"], t["anchor"])
    points = [spos] + [(wp["x"], wp["y"]) for wp in conn.get("waypoints", [])] + [tpos]
    # Tolerância de sub-pixel (não de célula): posições de anchor vêm de
    # frações de largura de sprite (ex: cyl_width/2), então dois pontos
    # "no mesmo eixo" podem diferir por um resíduo de ponto flutuante
    # (< 0.1px) sem que o segmento seja visualmente diagonal.
    EPS = 0.5
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        assert abs(x0 - x1) < EPS or abs(y0 - y1) < EPS, (
            f"segmento diagonal em {s['node']}.{s['anchor']} -> "
            f"{t['node']}.{t['anchor']}: ({x0},{y0}) -> ({x1},{y1})"
        )


class TestNoNodeAtOrigin:
    def test_simple_sequence_no_node_stuck_at_zero_zero(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        for n in data["nodes"]:
            assert (n["position"]["x"], n["position"]["y"]) != (0, 0), n["id"]

    def test_multi_cycle_sequence_no_node_stuck_at_zero_zero(self):
        data = layout.apply(sbe.generate(parse("A+B+A-A+B-A-")))
        for n in data["nodes"]:
            assert (n["position"]["x"], n["position"]["y"]) != (0, 0), n["id"]


class TestRoleRemoved:
    def test_no_node_keeps_role_key(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        assert all("_role" not in n for n in data["nodes"])


class TestZoneOrdering:
    """Zona 2 (reset+bobina) fica inteira à direita da Zona 1 (ramo A/B),
    mesma faixa Y -- confirmado com o usuário."""

    def test_zone2_entirely_right_of_zone1(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))  # 4 átomos
        zone1_xs = []
        zone2_xs = []
        for k in range(4):
            zone1_xs.append(_node(data, f"gen-contact-{k}-ramo_a_prev")["position"]["x"])
            zone1_xs.append(_node(data, f"gen-contact-{k}-ramo_b_self")["position"]["x"])
            zone2_xs.append(_node(data, f"gen-contact-{k}-reset_nc")["position"]["x"])
            zone2_xs.append(_node(data, f"gen-coil-{k}")["position"]["x"])
        assert max(zone1_xs) < min(zone2_xs)

    def test_zone1_and_zone2_same_y_band(self):
        # ramo_row e reset_row/coil_row ficam na mesma faixa vertical da Zona
        # 1 -- reset_row tem o mesmo Y que ramo_row (não abaixo dela).
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        ramo_b_y = _node(data, "gen-contact-0-ramo_b_self")["position"]["y"]
        reset_y = _node(data, "gen-contact-0-reset_nc")["position"]["y"]
        assert ramo_b_y == reset_y

    def test_atoms_ordered_left_to_right_in_zone1(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        xs = [_node(data, f"gen-contact-{k}-ramo_b_self")["position"]["x"] for k in range(4)]
        assert xs == sorted(xs)

    def test_atoms_ordered_left_to_right_in_zone2(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        xs = [_node(data, f"gen-coil-{k}")["position"]["x"] for k in range(4)]
        assert xs == sorted(xs)


class TestVoltageSourceAboveGroundBelow:
    def test_voltage_source_above_ramo_row(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        vsource_y = _node(data, "gen-vsource")["position"]["y"]
        ramo_y = _node(data, "gen-contact-0-ramo_b_self")["position"]["y"]
        assert vsource_y < ramo_y

    def test_ground_below_ramo_row(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        ground_y = _node(data, "gen-ground")["position"]["y"]
        ramo_y = _node(data, "gen-contact-0-ramo_b_self")["position"]["y"]
        assert ground_y > ramo_y


class TestCylinderRegionAboveElectricRegion:
    def test_cylinders_above_voltage_source(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        cyl_y = _node(data, "gen-cyl-A")["position"]["y"]
        vsource_y = _node(data, "gen-vsource")["position"]["y"]
        assert cyl_y < vsource_y


class TestLayoutMapRegistration:
    def test_generate_and_load_resolves_electric_layout(self):
        from circuit_generator.circuit_generator import LAYOUT_MAP
        assert LAYOUT_MAP[("step_by_step", "electric")] is layout.apply


class TestWaypoints:
    def test_at_least_some_connections_get_waypoints(self):
        # Não toda conexão precisa de waypoint (linhas retas curtas não
        # geram nenhum) -- mas um circuito deste tamanho, com a Zona 2
        # deslocada bem à direita da Zona 1, tem que produzir pelo menos
        # algumas travessias longas com dobra.
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        assert any("waypoints" in c for c in data["connections"])


class TestVoltageSourceGroundBarDimensioned:
    """Finding 2 da revisão final: as barras VoltageSource/Ground precisam
    cobrir o alcance real do circuito (grid.occupied_x_range()), não só os
    poucos anchors que a topologia atribuiu -- ver seção "Barras
    VoltageSource/Ground" do design doc."""

    def test_bars_span_at_least_the_full_x_range_of_nodes(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        node_xs = [n["position"]["x"] for n in data["nodes"]]
        min_x, max_x = min(node_xs), max(node_xs)

        for bus_id in ("gen-vsource", "gen-ground"):
            n = _node(data, bus_id)
            anchors = n["properties"]["anchors"]
            assert len(anchors) >= 2
            # A barra em si (não o 1o anchor, que já nasce deslocado do
            # corpo -- ver vsource_pix_w/ground_pix_w em _scene_xy) já
            # começa na borda esquerda do circuito -- só o lado direito
            # depende do array de anchors ter crescido o suficiente.
            assert n["position"]["x"] <= min_x + 1
            last_x, _ = _scene_xy(data, bus_id, anchors[-1])
            assert last_x >= max_x - 1

    def test_bars_grow_only_never_shrink_existing_anchors(self):
        # As conexões da topologia já referenciam anchors por índice/nome --
        # crescer o array só pode APENDAR no final, nunca remover/renomear
        # os que já existem (mesmo princípio "nunca encolhe" do pneumático).
        raw = sbe.generate(parse("A+B+A-B-"))
        vs_before = next(n for n in raw["nodes"] if n["id"] == "gen-vsource")
        original_anchors = list(vs_before["properties"]["anchors"])

        data = layout.apply(raw)
        vs_after = _node(data, "gen-vsource")
        grown_anchors = vs_after["properties"]["anchors"]

        assert grown_anchors[: len(original_anchors)] == original_anchors
        assert len(grown_anchors) >= len(original_anchors)


class TestPilotSigChainPlacement:
    """Finding 1/3 da revisão final: cada pilot_sig de uma cadeia
    multi-ciclo precisa de coluna própria (nunca empilhada com outra) e a
    conexão sig -> OrValve/Valve_4_2_Ways precisa ser roteável
    ortogonalmente -- ver _place_pilot_sig_chain(). Sequência de referência
    do plano: parse("A+B+A-A+B-A-"), onde A+ ocorre nos átomos 0 e 3, A- nos
    átomos 2 e 5."""

    SEQ = "A+B+A-A+B-A-"

    def _pilot_sig_ids(self, raw):
        return [n["id"] for n in raw["nodes"] if n["_role"].startswith("pilot_sig:")]

    def test_every_pilot_sig_gets_a_distinct_position(self):
        # sig_ids precisa vir do MESMO dict que layout.apply() recebe --
        # generate() usa uuid4 pros ids, então duas chamadas separadas
        # produzem ids diferentes e um segundo generate() não teria
        # correspondência com os nós já posicionados pelo primeiro.
        raw = sbe.generate(parse(self.SEQ))
        sig_ids = self._pilot_sig_ids(raw)
        assert len(sig_ids) >= 2  # sequência de referência tem 4 (2 por lado)

        data = layout.apply(raw)
        positions = [
            (_node(data, sid)["position"]["x"], _node(data, sid)["position"]["y"])
            for sid in sig_ids
        ]
        assert len(set(positions)) == len(positions), positions

    def test_sig_to_or_or_v42_connections_are_orthogonal(self):
        raw = sbe.generate(parse(self.SEQ))
        sig_ids = set(self._pilot_sig_ids(raw))

        data = layout.apply(raw)
        node_type = {n["id"]: n["type"] for n in data["nodes"]}

        checked = 0
        for conn in data["connections"]:
            s_id, t_id = conn["source"]["node"], conn["target"]["node"]
            s_is_sig = s_id in sig_ids and node_type.get(s_id) == "Valve_3_2_Ways"
            if not s_is_sig:
                continue
            if node_type.get(t_id) not in ("OrValve", "Valve_4_2_Ways"):
                continue
            _assert_connection_orthogonal(data, conn)
            checked += 1
        assert checked >= 2  # pelo menos as 2 cadeias (A+ e A-) da sequência


class TestAllConnectionsOrthogonal:
    """Finding 4 da revisão final: invariante geral do codebase -- toda
    conexão do circuito, depois do layout, é ortogonal (waypoints ou reta
    de eixo único), nunca diagonal. Verificado em múltiplas sequências:
    simples, multi-ciclo (o caso que o Finding 1 corrigiu) e bloco
    paralelo."""

    @pytest.mark.parametrize("seq", [
        "A+B+A-B-",
        "A+B+A-A+B-A-",
        "C+(A+B+)C-A-B-",
    ])
    def test_no_diagonal_connections(self, seq):
        data = layout.apply(sbe.generate(parse(seq)))
        assert data["connections"], "circuito de teste sem nenhuma conexão"
        for conn in data["connections"]:
            _assert_connection_orthogonal(data, conn)
