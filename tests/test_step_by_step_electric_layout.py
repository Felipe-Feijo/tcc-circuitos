"""Testes para circuit_generator/step_by_step_electric_layout.py — ver
docs/superpowers/specs/2026-07-30-step-by-step-electric-layout-design.md
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.sequence_parser import parse
from circuit_generator.methods import step_by_step_electric as sbe
from circuit_generator import step_by_step_electric_layout as layout


def _node(data, node_id):
    return next(n for n in data["nodes"] if n["id"] == node_id)


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
