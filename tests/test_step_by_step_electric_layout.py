"""Testes para circuit_generator/step_by_step_electric_layout.py — ver
docs/superpowers/specs/2026-07-31-step-by-step-electric-power-contacts-design.md
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

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


class TestNoNodeAtOrigin:
    def test_simple_sequence_no_node_stuck_at_zero_zero(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        for n in data["nodes"]:
            if n["id"] == "gen-cyl-A":
                continue  # legítimo: primeira coluna/primeira linha do grid
            assert (n["position"]["x"], n["position"]["y"]) != (0, 0), n["id"]

    def test_multi_cycle_sequence_no_node_stuck_at_zero_zero(self):
        data = layout.apply(sbe.generate(parse("A+B+A-A+B-A-")))
        for n in data["nodes"]:
            if n["id"] == "gen-cyl-A":
                continue
            assert (n["position"]["x"], n["position"]["y"]) != (0, 0), n["id"]


class TestRoleRemoved:
    def test_no_node_keeps_role_key(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        assert all("_role" not in n for n in data["nodes"])


class TestZoneOrdering:
    """Zona 3 (potência) fica inteira à direita da Zona 2 (reset+K), que
    fica inteira à direita da Zona 1 (ramo A/B) -- todas na mesma faixa Y."""

    def test_zone3_entirely_right_of_zone2(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        zone2_xs = [_node(data, f"gen-contact-{k}-reset_nc")["position"]["x"] for k in range(4)]
        zone3_xs = [_node(data, cid)["position"]["x"] for cid in (
            "gen-contact-power-A-ext-0", "gen-contact-power-B-ext-1",
            "gen-contact-power-A-ret-2", "gen-contact-power-B-ret-3",
        )]
        assert max(zone2_xs) < min(zone3_xs)

    def test_zone2_entirely_right_of_zone1(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        zone1_xs = []
        zone2_xs = []
        for k in range(4):
            zone1_xs.append(_node(data, f"gen-contact-{k}-ramo_a_prev")["position"]["x"])
            zone1_xs.append(_node(data, f"gen-contact-{k}-ramo_b_self")["position"]["x"])
            zone2_xs.append(_node(data, f"gen-contact-{k}-reset_nc")["position"]["x"])
            zone2_xs.append(_node(data, f"gen-coil-{k}")["position"]["x"])
        assert max(zone1_xs) < min(zone2_xs)

    def test_all_zones_same_y_band(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        ramo_b_y = _node(data, "gen-contact-0-ramo_b_self")["position"]["y"]
        reset_y = _node(data, "gen-contact-0-reset_nc")["position"]["y"]
        power_y = _node(data, "gen-contact-power-A-ext-0")["position"]["y"]
        assert ramo_b_y == reset_y == power_y

    def test_power_groups_ordered_by_first_triggering_atom(self):
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))  # A+(k0), B+(k1), A-(k2), B-(k3)
        xs = {
            "gen-contact-power-A-ext-0": _node(data, "gen-contact-power-A-ext-0")["position"]["x"],
            "gen-contact-power-B-ext-1": _node(data, "gen-contact-power-B-ext-1")["position"]["x"],
            "gen-contact-power-A-ret-2": _node(data, "gen-contact-power-A-ret-2")["position"]["x"],
            "gen-contact-power-B-ret-3": _node(data, "gen-contact-power-B-ret-3")["position"]["x"],
        }
        ordered = sorted(xs, key=lambda cid: xs[cid])
        assert ordered == [
            "gen-contact-power-A-ext-0", "gen-contact-power-B-ext-1",
            "gen-contact-power-A-ret-2", "gen-contact-power-B-ret-3",
        ]


class TestMultiCyclePowerStacking:
    """A+B+A-A+B-A- -- A+ dispara nos átomos 0 e 3: 2 contatos de potência
    empilhados na MESMA sub-coluna (nunca dividindo célula, mesma técnica
    já usada pra sensores empilhados na Zona 1)."""

    def test_two_power_contacts_distinct_positions_same_column(self):
        data = layout.apply(sbe.generate(parse("A+B+A-A+B-A-")))
        c0 = _node(data, "gen-contact-power-A-ext-0")["position"]
        c3 = _node(data, "gen-contact-power-A-ext-3")["position"]
        assert c0 != c3
        assert c0["x"] == c3["x"]  # mesma sub-coluna
        assert c0["y"] != c3["y"]  # profundidades diferentes

    def test_y_coil_position_distinct_from_its_contacts(self):
        data = layout.apply(sbe.generate(parse("A+B+A-A+B-A-")))
        coil = _node(data, "gen-ycoil-A-ext")["position"]
        c0 = _node(data, "gen-contact-power-A-ext-0")["position"]
        assert coil != c0


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

    def test_cylinders_one_column_each_no_gap_reservation(self):
        # Sem OrValve no gerador elétrico -- sempre 1 coluna por letra.
        data = layout.apply(sbe.generate(parse("A+B+A-B-")))
        cyl_a_x = _node(data, "gen-cyl-A")["position"]["x"]
        cyl_b_x = _node(data, "gen-cyl-B")["position"]["x"]
        assert cyl_b_x - cyl_a_x == 300  # cyl_cell_w, sem reserva extra


class TestLayoutMapRegistration:
    def test_generate_and_load_resolves_electric_layout(self):
        from circuit_generator.circuit_generator import LAYOUT_MAP
        assert LAYOUT_MAP[("step_by_step", "electric")] is layout.apply


class TestAllConnectionsOrthogonal:
    def test_no_diagonal_connections(self):
        for seq in ("A+B+A-B-", "A+B+A-A+B-A-", "C+(A+B+)C-A-B-"):
            data = layout.apply(sbe.generate(parse(seq)))
            for conn in data["connections"]:
                _assert_connection_orthogonal(data, conn)
