"""Testes para circuit_generator/methods/step_by_step_electric.py — ver
docs/superpowers/specs/2026-07-30-step-by-step-electric-design.md
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from circuit_generator.sequence_parser import parse
from circuit_generator.methods import step_by_step_electric as sbe
from circuit_generator.methods.step_by_step_electric import _atomize


def _conns_from(data, node_id, anchor=None):
    return [c for c in data["connections"]
            if c["source"]["node"] == node_id
            and (anchor is None or c["source"]["anchor"] == anchor)]


def _conns_to(data, node_id, anchor=None):
    return [c for c in data["connections"]
            if c["target"]["node"] == node_id
            and (anchor is None or c["target"]["anchor"] == anchor)]


def _node(data, node_id):
    return next(n for n in data["nodes"] if n["id"] == node_id)


class TestAtomize:
    def test_no_parallel_ids_each_event_is_its_own_atom(self):
        events = [("A", "+", None), ("B", "+", None)]
        assert _atomize(events) == [
            [(0, "A", "+")],
            [(1, "B", "+")],
        ]

    def test_single_block_is_one_atom(self):
        events = [("A", "+", 0), ("B", "+", 0)]
        assert _atomize(events) == [
            [(0, "A", "+"), (1, "B", "+")],
        ]


class TestBoilerplate:
    def test_cylinders_and_v42_created_for_each_letter(self):
        data = sbe.generate(parse("A+B+A-B-"))
        cyl_ids = {n["id"] for n in data["nodes"] if n["type"] == "DoubleActingCylinder"}
        v42_ids = {n["id"] for n in data["nodes"] if n["type"] == "Valve_4_2_Ways"}
        assert cyl_ids == {"gen-cyl-A", "gen-cyl-B"}
        assert v42_ids == {"gen-v42-A", "gen-v42-B"}

    def test_v42_has_dedicated_pressure_source_and_exhaust(self):
        data = sbe.generate(parse("A+B+A-B-"))
        p_source = _conns_to(data, "gen-v42-A", "R")
        r_exhaust = _conns_to(data, "gen-v42-A", "P")
        assert len(p_source) == 1 and _node(data, p_source[0]["source"]["node"])["type"] == "PressureSource"
        assert len(r_exhaust) == 1 and _node(data, r_exhaust[0]["source"]["node"])["type"] == "Exhaust"

    def test_electric_bus_nodes_created_with_electric_domain(self):
        data = sbe.generate(parse("A+B+A-B-"))
        vsource = _node(data, "gen-vsource")
        ground = _node(data, "gen-ground")
        btn = _node(data, "gen-btn")
        assert vsource["type"] == "VoltageSource" and vsource["domain"] == "electric"
        assert ground["type"] == "Ground" and ground["domain"] == "electric"
        assert btn["type"] == "ButtonSwitch" and btn["domain"] == "electric"
        assert btn["properties"]["contact_type"] == "NO"


class TestCoilRing:
    def test_one_solenoid_coil_per_atom_with_sequential_sensor_names(self):
        data = sbe.generate(parse("A+B+A-B-"))  # 4 átomos de 1 evento
        coil_ids = {n["id"] for n in data["nodes"] if n["type"] == "SolenoidCoil"}
        assert coil_ids == {"gen-coil-0", "gen-coil-1", "gen-coil-2", "gen-coil-3"}
        for k in range(4):
            coil = _node(data, f"gen-coil-{k}")
            assert coil["domain"] == "electric"
            assert coil["properties"]["sensor"]["coil"]["name"] == f"Y{k + 1}"

    def test_parallel_block_is_a_single_atom_with_one_coil(self):
        data = sbe.generate(parse("C+(A+B+)C-A-B-"))  # 5 átomos
        coil_ids = {n["id"] for n in data["nodes"] if n["type"] == "SolenoidCoil"}
        assert coil_ids == {f"gen-coil-{k}" for k in range(5)}


class TestRungWiring:
    """A+B+A-B- -- 4 átomos, cada um 1 evento só."""

    def test_reset_contact_is_nc_and_wired_to_next_coil(self):
        data = sbe.generate(parse("A+B+A-B-"))
        for k in range(4):
            next_k = (k + 1) % 4
            reset = _node(data, f"gen-contact-{k}-reset_nc")
            assert reset["type"] == "RelaySwitch"
            assert reset["properties"]["contact_type"] == "NC"
            assert reset["properties"]["relay_sensor"] == f"Y{next_k + 1}"

    def test_reset_contact_receives_both_branches(self):
        data = sbe.generate(parse("A+B+A-B-"))
        incoming = _conns_to(data, "gen-contact-0-reset_nc", "T")
        sources = {c["source"]["node"] for c in incoming}
        assert sources == {"gen-contact-0-ramo_a_prev", "gen-contact-0-ramo_b_self"}

    def test_ramo_a_prev_contact_references_previous_atom_coil_ring_wraps(self):
        data = sbe.generate(parse("A+B+A-B-"))
        expected = {0: "Y4", 1: "Y1", 2: "Y2", 3: "Y3"}  # ring: atom 0 volta pro último
        for k, y in expected.items():
            n = _node(data, f"gen-contact-{k}-ramo_a_prev")
            assert n["properties"]["relay_sensor"] == y
            assert n["properties"]["contact_type"] == "NO"

    def test_ramo_b_self_hold_references_own_coil(self):
        data = sbe.generate(parse("A+B+A-B-"))
        for k in range(4):
            n = _node(data, f"gen-contact-{k}-ramo_b_self")
            assert n["properties"]["relay_sensor"] == f"Y{k + 1}"
            assert n["properties"]["contact_type"] == "NO"

    def test_ramo_a_single_event_atom_uses_one_sensor_contact(self):
        # átomo anterior ao 1 é o átomo 0 (A+), 1 evento só -> 1 contato de sensor.
        data = sbe.generate(parse("A+B+A-B-"))
        sensor_contact = _node(data, "gen-contact-1-ramo_a_sensor0")
        assert sensor_contact["properties"]["contact_type"] == "NO"
        assert sensor_contact["properties"]["relay_sensor"] == "a1"  # confirm_sensor("A","+")
        out = _conns_from(data, "gen-contact-1-ramo_a_sensor0", "B")
        assert out[0]["target"]["node"] == "gen-contact-1-ramo_a_prev"

    def test_ramo_a_parallel_atom_chains_sensor_contacts_in_series(self):
        data = sbe.generate(parse("C+(A+B+)C-A-B-"))  # átomo 2 (C-) segue o átomo 1 ((A+B+))
        s0 = _node(data, "gen-contact-2-ramo_a_sensor0")
        s1 = _node(data, "gen-contact-2-ramo_a_sensor1")
        assert {s0["properties"]["relay_sensor"], s1["properties"]["relay_sensor"]} == {"a1", "b1"}
        chain = _conns_from(data, "gen-contact-2-ramo_a_sensor0", "B")
        assert chain[0]["target"]["node"] == "gen-contact-2-ramo_a_sensor1"
        assert chain[0]["target"]["anchor"] == "T"
        tail = _conns_from(data, "gen-contact-2-ramo_a_sensor1", "B")
        assert tail[0]["target"]["node"] == "gen-contact-2-ramo_a_prev"

    def test_coil_fed_from_reset_contact_and_drains_to_ground(self):
        data = sbe.generate(parse("A+B+A-B-"))
        into_coil = _conns_to(data, "gen-coil-0", "T")
        assert len(into_coil) == 1
        assert into_coil[0]["source"]["node"] == "gen-contact-0-reset_nc"
        assert into_coil[0]["source"]["anchor"] == "B"

        out_of_coil = _conns_from(data, "gen-coil-0", "B")
        assert len(out_of_coil) == 1
        assert out_of_coil[0]["target"]["node"] == "gen-ground"

    def test_voltage_source_taps_feed_both_branch_starts(self):
        data = sbe.generate(parse("A+B+A-B-"))
        targets = {c["target"]["node"] for c in _conns_from(data, "gen-vsource")}
        # átomo 1: sensor contact inicial da cadeia + self-hold
        assert "gen-contact-1-ramo_a_sensor0" in targets
        assert "gen-contact-1-ramo_b_self" in targets


class TestBootstrap:
    def test_only_last_atom_gets_button_branch(self):
        data = sbe.generate(parse("A+B+A-B-"))  # 4 átomos, último é o 3
        btn_target = _conns_from(data, "gen-btn", "B")
        assert len(btn_target) == 1
        assert btn_target[0]["target"]["node"] == "gen-contact-3-reset_nc"

        for k in range(3):
            incoming = _conns_to(data, f"gen-contact-{k}-reset_nc", "T")
            sources = {c["source"]["node"] for c in incoming}
            assert "gen-btn" not in sources

    def test_last_atom_reset_contact_receives_three_branches(self):
        data = sbe.generate(parse("A+B+A-B-"))
        incoming = _conns_to(data, "gen-contact-3-reset_nc", "T")
        sources = {c["source"]["node"] for c in incoming}
        assert sources == {"gen-contact-3-ramo_a_prev", "gen-contact-3-ramo_b_self", "gen-btn"}

    def test_button_fed_from_voltage_source(self):
        data = sbe.generate(parse("A+B+A-B-"))
        into_btn = _conns_to(data, "gen-btn", "T")
        assert len(into_btn) == 1
        assert into_btn[0]["source"]["node"] == "gen-vsource"


class TestBusAnchors:
    def test_voltage_source_and_ground_anchors_grow_on_demand(self):
        data = sbe.generate(parse("A+B+A-B-"))
        vsource = _node(data, "gen-vsource")
        ground = _node(data, "gen-ground")
        touching_vsource = _conns_from(data, "gen-vsource")
        touching_ground = _conns_to(data, "gen-ground")
        assert len(vsource["properties"]["anchors"]) == len(touching_vsource)
        assert len(ground["properties"]["anchors"]) == len(touching_ground)

    def test_no_anchor_name_reused_within_the_same_bus(self):
        data = sbe.generate(parse("A+B+A-B-"))
        for n in data["nodes"]:
            if n["type"] in ("VoltageSource", "Ground"):
                anchors = n["properties"]["anchors"]
                assert len(anchors) == len(set(anchors))


class TestPilotWiringSingleOccurrence:
    """A+B+A-B- -- nenhum cilindro repete direção, então nenhuma sig/OrValve
    deve ser criada; o atuador da 4/2 lê o Y do átomo direto."""

    def test_v42_actuators_are_solenoid_direct(self):
        data = sbe.generate(parse("A+B+A-B-"))
        v42_a = _node(data, "gen-v42-A")
        v42_b = _node(data, "gen-v42-B")
        # A+ é o átomo 0 (Y1), A- é o átomo 2 (Y3)
        assert v42_a["properties"]["actuators"]["left"] == {"type": "solenoid", "sensor_name": "Y1"}
        assert v42_a["properties"]["actuators"]["right"] == {"type": "solenoid", "sensor_name": "Y3"}
        # B+ é o átomo 1 (Y2), B- é o átomo 3 (Y4)
        assert v42_b["properties"]["actuators"]["left"] == {"type": "solenoid", "sensor_name": "Y2"}
        assert v42_b["properties"]["actuators"]["right"] == {"type": "solenoid", "sensor_name": "Y4"}

    def test_no_pilot_sig_or_or_valve_created(self):
        data = sbe.generate(parse("A+B+A-B-"))
        assert [n for n in data["nodes"] if n["_role"].startswith("pilot_sig")] == []
        assert [n for n in data["nodes"] if n["type"] == "OrValve"] == []

    def test_full_node_and_connection_counts(self):
        data = sbe.generate(parse("A+B+A-B-"))
        assert len(data["nodes"]) == 31
        assert len(data["connections"]) == 38


class TestPilotWiringMultiCycle:
    """A+B+A-A+B-A- -- A+ ocorre nos átomos 0 e 3; A- ocorre nos átomos 2 e 5."""

    def test_v42_a_actuators_become_pneumatic_pilot(self):
        data = sbe.generate(parse("A+B+A-A+B-A-"))
        v42_a = _node(data, "gen-v42-A")
        assert v42_a["properties"]["actuators"]["left"] == {"type": "pneumatic_pilot"}
        assert v42_a["properties"]["actuators"]["right"] == {"type": "pneumatic_pilot"}

    def test_v42_b_actuators_stay_solenoid_direct(self):
        data = sbe.generate(parse("A+B+A-A+B-A-"))
        v42_b = _node(data, "gen-v42-B")
        assert v42_b["properties"]["actuators"]["left"] == {"type": "solenoid", "sensor_name": "Y2"}
        assert v42_b["properties"]["actuators"]["right"] == {"type": "solenoid", "sensor_name": "Y5"}

    def test_two_pilot_sigs_per_repeated_direction_each_reading_own_coil(self):
        data = sbe.generate(parse("A+B+A-A+B-A-"))
        s0 = _node(data, "gen-pilot-sig-A-ext-0")
        s3 = _node(data, "gen-pilot-sig-A-ext-3")
        assert s0["properties"]["actuators"]["left"] == {"type": "solenoid", "sensor_name": "Y1"}
        assert s3["properties"]["actuators"]["left"] == {"type": "solenoid", "sensor_name": "Y4"}
        assert s0["properties"]["actuators"]["right"] == {"type": "spring"}

    def test_pilot_sig_has_dedicated_pressure_source_and_exhaust(self):
        data = sbe.generate(parse("A+B+A-A+B-A-"))
        p_in = _conns_to(data, "gen-pilot-sig-A-ext-0", "P")
        r_out = _conns_from(data, "gen-pilot-sig-A-ext-0", "R")
        assert len(p_in) == 1 and _node(data, p_in[0]["source"]["node"])["type"] == "PressureSource"
        assert len(r_out) == 1 and _node(data, r_out[0]["target"]["node"])["type"] == "Exhaust"

    def test_or_valve_merges_the_two_pilot_sigs_and_feeds_v42_pilot(self):
        data = sbe.generate(parse("A+B+A-A+B-A-"))
        or_nodes = [n for n in data["nodes"] if n["type"] == "OrValve"]
        assert len(or_nodes) == 2  # 1 pra PL de A, 1 pra PR de A

        pl_or = next(n for n in or_nodes if n["_role"] == "or_valve:A:PL:0")
        x_conn = next(c for c in data["connections"]
                      if c["target"]["node"] == pl_or["id"] and c["target"]["anchor"] == "X")
        y_conn = next(c for c in data["connections"]
                      if c["target"]["node"] == pl_or["id"] and c["target"]["anchor"] == "Y")
        assert {x_conn["source"]["node"], y_conn["source"]["node"]} == {
            "gen-pilot-sig-A-ext-0", "gen-pilot-sig-A-ext-3",
        }
        out_conn = next(c for c in data["connections"] if c["source"]["node"] == pl_or["id"])
        assert out_conn == {
            "source": {"node": pl_or["id"], "anchor": "A"},
            "target": {"node": "gen-v42-A", "anchor": "PL"},
        }

    def test_full_node_and_connection_counts(self):
        data = sbe.generate(parse("A+B+A-A+B-A-"))
        assert len(data["nodes"]) == 55
        assert len(data["connections"]) == 66


class TestMinimumAtomCount:
    def test_two_atom_sequence_raises_value_error(self):
        with pytest.raises(ValueError):
            sbe.generate(parse("A+A-"))


class TestPilotWiringParallelBlock:
    def test_full_node_and_connection_counts(self):
        data = sbe.generate(parse("C+(A+B+)C-A-B-"))
        assert len(data["nodes"]) == 41
        assert len(data["connections"]) == 50

    def test_no_or_valve_no_repeats(self):
        data = sbe.generate(parse("C+(A+B+)C-A-B-"))
        assert [n for n in data["nodes"] if n["type"] == "OrValve"] == []
