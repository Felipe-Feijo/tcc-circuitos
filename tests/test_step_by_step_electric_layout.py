"""Testes para circuit_generator/step_by_step_electric_layout.py — ver
docs/superpowers/specs/2026-07-31-step-by-step-electric-start-button-and-anchor-fix-design.md
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
        data = layout.apply(sbe.generate(parse("C+(A+B+)C-A-B-")))
        vsource_y = _node(data, "gen-vsource")["position"]["y"]
        sensor_y = _node(data, "gen-contact-2-ramo_a_sensor0")["position"]["y"]
        assert vsource_y != sensor_y

    def test_voltage_source_does_not_overlap_a_3_deep_sensor_stack(self):
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


class TestStartButtonPosition:
    """Botão de início: mesma coluna do ramo A do átomo 0, numa linha
    própria entre ramo_row e reset_row."""

    def test_start_button_same_column_as_atom_zero_ramo_a(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        ramo_a_x = _node(data, "gen-contact-0-ramo_a_prev")["position"]["x"]
        btn_x = _node(data, "gen-btn-start")["position"]["x"]
        assert btn_x == ramo_a_x

    def test_start_button_between_ramo_row_and_reset_row(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        ramo_y = _node(data, "gen-contact-0-ramo_a_prev")["position"]["y"]
        reset_y = _node(data, "gen-contact-0-reset_nc")["position"]["y"]
        btn_y = _node(data, "gen-btn-start")["position"]["y"]
        assert ramo_y < btn_y < reset_y


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
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
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
    def test_reassignment_fixes_a_deliberately_scrambled_default_order(self):
        seq = "A+B+A-B-"
        raw = sbe.generate(parse(seq))
        vsource_conns = [c for c in raw["connections"] if c["source"]["node"] == "gen-vsource"]
        assert len(vsource_conns) >= 2, "sequência de teste não gerou conexões suficientes"
        first, last = vsource_conns[0], vsource_conns[-1]
        first["target"], last["target"] = last["target"], first["target"]
        naive_anchor_snapshot = [(c["source"]["anchor"], c["target"]["node"]) for c in vsource_conns]

        data = layout.apply(raw)
        node_by_id = {n["id"]: n for n in data["nodes"]}
        vsource = _node(data, "gen-vsource")
        anchors = vsource["properties"]["anchors"]

        def anchor_x(name):
            idx = anchors.index(name)
            return vsource["position"]["x"] + _M.vsource_pix_w + idx * _M.pl_spacing

        naive_rows = sorted(
            (anchor_x(a), node_by_id[target_id]["position"]["x"])
            for a, target_id in naive_anchor_snapshot
        )
        naive_target_xs = [r[1] for r in naive_rows]
        assert naive_target_xs != sorted(naive_target_xs), (
            "cenário sintético não ficou scrambled -- ajustar a troca de targets"
        )

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
    def test_vsource_anchor_indices_spread_beyond_leftmost_prefix(self):
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
        assert max(used_indices) > (m - 1) // 2, (
            f"anchors usados ({used_indices}) não se espalham além do "
            f"prefixo mais à esquerda de {m} anchors disponíveis"
        )


class TestBusAnchorsGenuinelyNearest:
    """Achado de revisão: o espalhamento por índice proporcional (ranking)
    ignora a posição real quando a distribuição dos targets não é uniforme
    -- o vão grande entre os blocos de átomo e a zona de potência produzia
    erro de até 1530px numa sequência de 12 átomos. A busca de vizinho mais
    próximo real reduz isso a ~70px (o termo de offset fixo da própria
    fórmula da anchor, não um erro de escolha)."""

    def test_max_anchor_target_delta_stays_small(self):
        data = layout.apply(sbe.generate(parse("A+B+C+A-B-C-A+B+C+A-B-C-")))
        vsource = _node(data, "gen-vsource")
        anchors = vsource["properties"]["anchors"]
        node_by_id = {n["id"]: n for n in data["nodes"]}

        def anchor_x(name):
            idx = anchors.index(name)
            return vsource["position"]["x"] + _M.vsource_pix_w + idx * _M.pl_spacing

        max_delta = 0.0
        for c in data["connections"]:
            if c["source"]["node"] == "gen-vsource":
                ax = anchor_x(c["source"]["anchor"])
                tx = node_by_id[c["target"]["node"]]["position"]["x"]
                max_delta = max(max_delta, abs(ax - tx))
        assert max_delta < 200, f"max delta {max_delta} -- esperado bem abaixo de 200px"


class TestAllConnectionsOrthogonal:
    @pytest.mark.parametrize("seq", ["A+B+A-B-", "A+B+A-A+B-A-", "C+(A+B+)C-A-B-"])
    def test_no_diagonal_connections(self, seq):
        data = layout.apply(sbe.generate(parse(seq)))
        assert data["connections"], "circuito de teste sem nenhuma conexão"
        for conn in data["connections"]:
            _assert_connection_orthogonal(data, conn)


class TestRegressionCounts:
    @pytest.mark.parametrize("seq,n_nodes,n_conns", [
        ("A+B+A-B-", 40, 51),
        ("C+(A+B+)C-A-B-", 54, 69),
        ("A+B+A-A+B-A-", 52, 69),
    ])
    def test_node_and_connection_counts_unchanged_from_topology(self, seq, n_nodes, n_conns):
        data = layout.apply(sbe.generate(parse(seq)))
        assert len(data["nodes"]) == n_nodes
        assert len(data["connections"]) == n_conns
