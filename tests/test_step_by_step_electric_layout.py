"""Testes para circuit_generator/step_by_step_electric_layout.py — ver
docs/superpowers/specs/2026-07-31-step-by-step-electric-layout-v1-design.md
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

import pytest

from circuit_generator.sequence_parser import parse
from circuit_generator.methods import step_by_step_electric as sbe
from circuit_generator import step_by_step_electric_layout as layout
from circuit_generator.sprite_metrics import METRICS as _M, anchor_local_for_routing


def _node(data, node_id):
    return next(n for n in data["nodes"] if n["id"] == node_id)


def _scene_xy(node_by_id, node_type_map, node_id, anchor_name):
    pos = node_by_id[node_id]["position"]
    ntype = node_type_map.get(node_id, "")
    if ntype == "VoltageSource" and anchor_name.startswith("X"):
        anchors = node_by_id[node_id]["properties"]["anchors"]
        idx = anchors.index(anchor_name)
        return (pos["x"] + _M.vsource_pix_w + idx * _M.pl_spacing,
                pos["y"] + _M.vsource_pix_h * 69 / 100)
    if ntype == "Ground" and anchor_name.startswith("X"):
        anchors = node_by_id[node_id]["properties"]["anchors"]
        idx = anchors.index(anchor_name)
        return (pos["x"] + _M.ground_pix_w * 0.5 + idx * _M.pl_spacing, pos["y"])
    local = anchor_local_for_routing(ntype, anchor_name)
    return (pos["x"] + local[0], pos["y"] + local[1]) if local else (pos["x"], pos["y"])


def _assert_connection_orthogonal(data, conn, eps=0.5):
    node_by_id = {n["id"]: n for n in data["nodes"]}
    node_type_map = {n["id"]: n["type"] for n in data["nodes"]}
    pts = [_scene_xy(node_by_id, node_type_map, conn["source"]["node"], conn["source"]["anchor"])]
    for wp in conn.get("waypoints", []):
        pts.append((wp["x"], wp["y"]))
    pts.append(_scene_xy(node_by_id, node_type_map, conn["target"]["node"], conn["target"]["anchor"]))
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        assert abs(x1 - x2) <= eps or abs(y1 - y2) <= eps, (
            f"diagonal segment {pts[i]} -> {pts[i + 1]} in connection {conn}"
        )


class TestCylinderSpacing:
    def test_cylinders_1000px_apart(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        cyl_a_x = _node(data, "gen-cyl-A")["position"]["x"]
        cyl_b_x = _node(data, "gen-cyl-B")["position"]["x"]
        assert cyl_b_x - cyl_a_x == 1000


class TestNoCollisionOrDuplicatePositions:
    def test_no_two_nodes_share_a_position(self):
        for seq in ("A+B+A-B-", "A+B+A-A+B-A-", "C+(A+B+)C-A-B-"):
            data = layout.apply(sbe.generate(parse(seq)))
            positions = [(n["position"]["x"], n["position"]["y"]) for n in data["nodes"]]
            assert len(positions) == len(set(positions)), seq

    def test_voltage_source_does_not_collide_with_ramo_a_stack(self):
        # Bug real do v0: vsource_row_y coincidia exatamente com a primeira
        # linha empilhada de sensores (ramo_row_y - 1*ramo_stack_gap).
        data = layout.apply(sbe.generate(parse("C+(A+B+)C-A-B-")))  # tem bloco paralelo -> stack
        vsource_y = _node(data, "gen-vsource")["position"]["y"]
        sensor_y = _node(data, "gen-contact-2-ramo_a_sensor0")["position"]["y"]
        assert vsource_y != sensor_y

    def test_voltage_source_does_not_overlap_a_3_deep_sensor_stack(self):
        # Achado de revisão: uma checagem de mera desigualdade de valor
        # (vsource_y != sensor_y) passa mesmo quando as CAIXAS DELIMITADORAS
        # dos dois sprites se sobrepõem -- e é exatamente isso que
        # acontecia com o stack de profundidade 3 sob as constantes
        # anteriores (vsource ocupava y em [700,800], stack de profundidade
        # 3 ocupava y em [750,825] -- 50px de sobreposição real). Este
        # teste verifica sobreposição de caixa delimitadora de verdade,
        # contra um átomo com 3 eventos simultâneos (bloco paralelo com 3
        # ramos).
        data = layout.apply(sbe.generate(parse("(A+B+C+)A-B-C-")))
        vsource = _node(data, "gen-vsource")
        vs_top = vsource["position"]["y"]
        vs_bottom = vs_top + _M.vsource_pix_h
        for role in ("ramo_a_sensor0", "ramo_a_sensor1", "ramo_a_sensor2"):
            sensor = _node(data, f"gen-contact-1-{role}")
            s_top = sensor["position"]["y"]
            s_bottom = s_top + _M.relay_switch_height
            overlap = s_top < vs_bottom and vs_top < s_bottom
            assert not overlap, (
                f"{role}: vsource=[{vs_top},{vs_bottom}] sensor=[{s_top},{s_bottom}]"
            )


class TestCoherentAtomBlock:
    """Reset (NC) e bobina K ficam na MESMA coluna do ramo B, logo abaixo
    -- bloco coeso por átomo, não mais uma zona distante."""

    def test_reset_and_coil_same_x_as_ramo_b(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        for k in range(4):
            ramo_b_x = _node(data, f"gen-contact-{k}-ramo_b_self")["position"]["x"]
            reset_x = _node(data, f"gen-contact-{k}-reset_nc")["position"]["x"]
            coil_x = _node(data, f"gen-coil-{k}")["position"]["x"]
            assert reset_x == ramo_b_x
            assert coil_x == ramo_b_x

    def test_reset_below_ramo_row_coil_below_reset(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        ramo_y = _node(data, "gen-contact-0-ramo_b_self")["position"]["y"]
        reset_y = _node(data, "gen-contact-0-reset_nc")["position"]["y"]
        coil_y = _node(data, "gen-coil-0")["position"]["y"]
        assert ramo_y < reset_y < coil_y

    def test_atom_blocks_ordered_left_to_right(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        xs = [_node(data, f"gen-contact-{k}-ramo_b_self")["position"]["x"] for k in range(4)]
        assert xs == sorted(xs)


class TestPowerZoneRightOfAllAtomBlocks:
    def test_power_zone_entirely_right_of_last_atom_block(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        atom_xs = []
        for k in range(4):
            atom_xs.append(_node(data, f"gen-contact-{k}-ramo_a_prev")["position"]["x"])
            atom_xs.append(_node(data, f"gen-contact-{k}-ramo_b_self")["position"]["x"])
            atom_xs.append(_node(data, f"gen-contact-{k}-reset_nc")["position"]["x"])
            atom_xs.append(_node(data, f"gen-coil-{k}")["position"]["x"])
        power_xs = [
            _node(data, cid)["position"]["x"] for cid in (
                "gen-contact-power-A-ext-0", "gen-contact-power-B-ext-1",
                "gen-contact-power-A-ret-2", "gen-contact-power-B-ret-3",
            )
        ]
        assert max(atom_xs) < min(power_xs)

    def test_power_groups_ordered_by_first_triggering_atom(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))  # A+(k0),B+(k1),A-(k2),B-(k3)
        xs = {
            cid: _node(data, cid)["position"]["x"] for cid in (
                "gen-contact-power-A-ext-0", "gen-contact-power-B-ext-1",
                "gen-contact-power-A-ret-2", "gen-contact-power-B-ret-3",
            )
        }
        ordered = sorted(xs, key=lambda cid: xs[cid])
        assert ordered == [
            "gen-contact-power-A-ext-0", "gen-contact-power-B-ext-1",
            "gen-contact-power-A-ret-2", "gen-contact-power-B-ret-3",
        ]


class TestMultiCyclePowerStacking:
    def test_two_power_contacts_distinct_positions_same_column(self):
        data = layout.apply(sbe.generate(parse("A+B+A-A+B-A-")))
        c0 = _node(data, "gen-contact-power-A-ext-0")["position"]
        c3 = _node(data, "gen-contact-power-A-ext-3")["position"]
        assert c0 != c3
        assert c0["x"] == c3["x"]
        assert c0["y"] != c3["y"]


class TestVoltageSourceAboveGroundBelow:
    def test_voltage_source_above_ramo_row(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        vsource_y = _node(data, "gen-vsource")["position"]["y"]
        ramo_y = _node(data, "gen-contact-0-ramo_b_self")["position"]["y"]
        assert vsource_y < ramo_y

    def test_ground_below_coil_row(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        ground_y = _node(data, "gen-ground")["position"]["y"]
        coil_y = _node(data, "gen-coil-0")["position"]["y"]
        assert ground_y > coil_y


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


class TestVoltageSourceGroundBarDimensioned:
    def test_bars_span_at_least_the_full_x_range_of_nodes(self):
        raw = sbe.generate(parse("A+B+A-B-"))
        data = layout.apply(raw)
        node_xs = [n["position"]["x"] for n in data["nodes"]]
        min_x, max_x = min(node_xs), max(node_xs)
        for bus_id in ("gen-vsource", "gen-ground"):
            node = _node(data, bus_id)
            anchors = node["properties"]["anchors"]
            last_scene_x = node["position"]["x"] + (len(anchors) - 1) * _M.pl_spacing
            assert node["position"]["x"] <= min_x
            assert last_scene_x >= max_x - _M.pl_spacing

    def test_bars_grow_only_never_shrink_existing_anchors(self):
        raw = sbe.generate(parse("A+B+A-B-"))
        original = {
            "gen-vsource": list(next(n for n in raw["nodes"] if n["id"] == "gen-vsource")["properties"]["anchors"]),
            "gen-ground": list(next(n for n in raw["nodes"] if n["id"] == "gen-ground")["properties"]["anchors"]),
        }
        data = layout.apply(raw)
        for bus_id, orig in original.items():
            grown = _node(data, bus_id)["properties"]["anchors"]
            assert grown[:len(orig)] == orig


class TestBusAnchorProximityReassignment:
    """Só existe UMA VoltageSource/Ground -- a reatribuição é um mapeamento
    monotônico: conexões ordenadas por X real do outro lado casam 1:1 com
    anchors ordenados por X real -- garante zero cruzamento por construção."""

    def test_voltage_source_anchor_assignment_is_monotonic_in_target_x(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        node_by_id = {n["id"]: n for n in data["nodes"]}
        vsource = _node(data, "gen-vsource")
        anchors = vsource["properties"]["anchors"]

        def anchor_x(name):
            idx = anchors.index(name)
            return vsource["position"]["x"] + _M.vsource_pix_w + idx * _M.pl_spacing

        rows = []
        for c in data["connections"]:
            if c["source"]["node"] == "gen-vsource":
                target_x = node_by_id[c["target"]["node"]]["position"]["x"]
                rows.append((anchor_x(c["source"]["anchor"]), target_x))
        rows.sort()
        target_xs = [r[1] for r in rows]
        assert target_xs == sorted(target_xs)

    def test_ground_anchor_assignment_is_monotonic_in_source_x(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        node_by_id = {n["id"]: n for n in data["nodes"]}
        ground = _node(data, "gen-ground")
        anchors = ground["properties"]["anchors"]

        def anchor_x(name):
            idx = anchors.index(name)
            return ground["position"]["x"] + _M.ground_pix_w * 0.5 + idx * _M.pl_spacing

        rows = []
        for c in data["connections"]:
            if c["target"]["node"] == "gen-ground":
                source_x = node_by_id[c["source"]["node"]]["position"]["x"]
                rows.append((anchor_x(c["target"]["anchor"]), source_x))
        rows.sort()
        source_xs = [r[1] for r in rows]
        assert source_xs == sorted(source_xs)


class TestBusAnchorReassignmentActuallyDoesSomething:
    """Achado de revisão: os dois testes acima só verificam que o resultado
    final é monotônico -- mas para TODA sequência real testável neste
    arquivo, a ordem de criação das conexões pelo gerador já é monotônica
    em X final (átomos e grupos de potência são sempre enumerados na mesma
    ordem esquerda->direita em que o layout os posiciona), então a
    reatribuição nunca muda nada observável por aqueles testes -- ela pode
    passar de forma idêntica com ou sem a reatribuição rodar. Este teste
    fabrica um cenário sintético (troca os `target` de duas conexões da
    VoltageSource antes de rodar layout.apply, criando deliberadamente uma
    ordem padrão NÃO monotônica) e confirma que layout.apply corrige isso
    -- prova de que o código de reatribuição realmente faz algo em vez de
    apenas preservar uma propriedade que já valia."""

    def test_reassignment_fixes_a_deliberately_scrambled_default_order(self):
        seq = "A+B+A-B-"
        raw = sbe.generate(parse(seq))
        vsource_conns = [c for c in raw["connections"] if c["source"]["node"] == "gen-vsource"]
        assert len(vsource_conns) >= 2, "sequência de teste não gerou conexões suficientes"
        first, last = vsource_conns[0], vsource_conns[-1]
        first["target"], last["target"] = last["target"], first["target"]
        # Snapshot do anchor ORIGINAL (pré-reatribuição, atribuído
        # sequencialmente pelo gerador) casado com o target já trocado --
        # isso é exatamente o mapeamento "ingênuo" que existiria se
        # layout.apply não reatribuísse nada.
        naive_anchor_snapshot = [(c["source"]["anchor"], c["target"]["node"]) for c in vsource_conns]

        data = layout.apply(raw)
        node_by_id = {n["id"]: n for n in data["nodes"]}
        vsource = _node(data, "gen-vsource")
        anchors = vsource["properties"]["anchors"]

        def anchor_x(name):
            idx = anchors.index(name)
            return vsource["position"]["x"] + _M.vsource_pix_w + idx * _M.pl_spacing

        # Pré-condição: confirma que o cenário sintético realmente scrambled
        # a ordem padrão -- senão este teste não provaria nada.
        naive_rows = sorted(
            (anchor_x(a), node_by_id[target_id]["position"]["x"])
            for a, target_id in naive_anchor_snapshot
        )
        naive_target_xs = [r[1] for r in naive_rows]
        assert naive_target_xs != sorted(naive_target_xs), (
            "cenário sintético não ficou scrambled -- ajustar a troca de targets"
        )

        # Pós-condição: layout.apply corrigiu a ordem.
        rows = []
        for c in data["connections"]:
            if c["source"]["node"] == "gen-vsource":
                target_x = node_by_id[c["target"]["node"]]["position"]["x"]
                rows.append((anchor_x(c["source"]["anchor"]), target_x))
        rows.sort()
        target_xs = [r[1] for r in rows]
        assert target_xs == sorted(target_xs), (
            "reatribuição não corrigiu a ordem sintética scrambled"
        )


class TestBusAnchorsSpreadAcrossFullRange:
    """Achado de revisão: zip(conns_sorted, anchors_sorted) truncava para o
    prefixo dos m anchors mais à esquerda quando havia menos conexões (n)
    que anchors disponíveis (m) -- a barra é dimensionada para cobrir toda
    a largura do circuito, mas ficava com a maior parte do comprimento sem
    uso, e componentes distantes (ex. x=3400) acabavam ligados a um anchor
    bem à esquerda (ex. x=790), um fio ~2600px maior que o necessário."""

    def test_vsource_anchor_indices_spread_beyond_leftmost_prefix(self):
        # Sequência com bloco paralelo -> barra fica bem mais larga (mais
        # anchors, m) do que o número de conexões da VoltageSource (n),
        # expondo o truncamento se ele ainda existisse.
        data = layout.apply(sbe.generate(parse("C+(A+B+)C-A-B-")))
        vsource = _node(data, "gen-vsource")
        anchors = vsource["properties"]["anchors"]
        m = len(anchors)
        used_indices = sorted(
            anchors.index(c["source"]["anchor"])
            for c in data["connections"]
            if c["source"]["node"] == "gen-vsource"
        )
        n = len(used_indices)
        assert n < m, "cenário de teste não tem folga entre n e m -- ajustar sequência"
        # Com o truncamento antigo, max(used_indices) == n - 1 sempre
        # (sempre os n anchors mais à esquerda). O comportamento corrigido
        # deve alcançar bem além disso -- usa pelo menos a metade superior
        # do range disponível.
        assert max(used_indices) > (m - 1) // 2, (
            f"anchors usados ({used_indices}) não se espalham além do "
            f"prefixo mais à esquerda de {m} anchors disponíveis"
        )


class TestAllConnectionsOrthogonal:
    @pytest.mark.parametrize("seq", ["A+B+A-B-", "A+B+A-A+B-A-", "C+(A+B+)C-A-B-"])
    def test_no_diagonal_connections(self, seq):
        data = layout.apply(sbe.generate(parse(seq)))
        assert data["connections"], "circuito de teste sem nenhuma conexão"
        for conn in data["connections"]:
            _assert_connection_orthogonal(data, conn)


class TestRegressionCounts:
    @pytest.mark.parametrize("seq,n_nodes,n_conns", [
        ("A+B+A-B-", 39, 50),
        ("C+(A+B+)C-A-B-", 53, 68),
        ("A+B+A-A+B-A-", 51, 68),
    ])
    def test_node_and_connection_counts_unchanged_from_topology(self, seq, n_nodes, n_conns):
        data = layout.apply(sbe.generate(parse(seq)))
        assert len(data["nodes"]) == n_nodes
        assert len(data["connections"]) == n_conns
