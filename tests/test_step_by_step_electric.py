"""Testes para circuit_generator/methods/step_by_step_electric.py — ver
docs/superpowers/specs/2026-07-31-step-by-step-electric-power-contacts-design.md
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

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


class TestMinimumAtomCount:
    def test_two_atom_sequence_raises_value_error(self):
        import pytest
        with pytest.raises(ValueError):
            sbe.generate(parse("A+A-"))


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


class TestLogicRing:
    def test_one_relay_coil_per_atom_with_sequential_sensor_names(self):
        data = sbe.generate(parse("A+B+A-B-"))  # 4 átomos de 1 evento
        coil_ids = {n["id"] for n in data["nodes"] if n["type"] == "RelayCoil"}
        assert coil_ids == {"gen-coil-0", "gen-coil-1", "gen-coil-2", "gen-coil-3"}
        for k in range(4):
            coil = _node(data, f"gen-coil-{k}")
            assert coil["domain"] == "electric"
            assert coil["properties"]["sensor"]["coil"]["name"] == f"K{k + 1}"

    def test_parallel_block_is_a_single_atom_with_one_coil(self):
        data = sbe.generate(parse("C+(A+B+)C-A-B-"))  # 5 átomos
        coil_ids = {n["id"] for n in data["nodes"] if n["type"] == "RelayCoil"}
        assert coil_ids == {f"gen-coil-{k}" for k in range(5)}


class TestRungWiring:
    """A+B+A-B- -- 4 átomos, cada um 1 evento só. Mesma topologia de degrau
    de antes, só os relay_sensor agora referenciam K em vez de Y."""

    def test_reset_contact_is_nc_and_wired_to_next_coil(self):
        data = sbe.generate(parse("A+B+A-B-"))
        for k in range(4):
            next_k = (k + 1) % 4
            reset = _node(data, f"gen-contact-{k}-reset_nc")
            assert reset["type"] == "RelaySwitch"
            assert reset["properties"]["contact_type"] == "NC"
            assert reset["properties"]["relay_sensor"] == f"K{next_k + 1}"

    def test_reset_contact_receives_both_branches(self):
        data = sbe.generate(parse("A+B+A-B-"))
        incoming = _conns_to(data, "gen-contact-0-reset_nc", "T")
        sources = {c["source"]["node"] for c in incoming}
        assert sources == {"gen-contact-0-ramo_a_prev", "gen-contact-0-ramo_b_self"}

    def test_ramo_a_prev_contact_references_previous_atom_coil_ring_wraps(self):
        data = sbe.generate(parse("A+B+A-B-"))
        expected = {0: "K4", 1: "K1", 2: "K2", 3: "K3"}  # ring: atom 0 volta pro último
        for k, kname in expected.items():
            n = _node(data, f"gen-contact-{k}-ramo_a_prev")
            assert n["properties"]["relay_sensor"] == kname
            assert n["properties"]["contact_type"] == "NO"

    def test_ramo_b_self_hold_references_own_coil(self):
        data = sbe.generate(parse("A+B+A-B-"))
        for k in range(4):
            n = _node(data, f"gen-contact-{k}-ramo_b_self")
            assert n["properties"]["relay_sensor"] == f"K{k + 1}"
            assert n["properties"]["contact_type"] == "NO"

    def test_coil_fed_from_reset_contact_and_drains_to_ground(self):
        data = sbe.generate(parse("A+B+A-B-"))
        into_coil = _conns_to(data, "gen-coil-0", "T")
        assert len(into_coil) == 1
        assert into_coil[0]["source"]["node"] == "gen-contact-0-reset_nc"
        assert into_coil[0]["source"]["anchor"] == "B"

        out_of_coil = _conns_from(data, "gen-coil-0", "B")
        assert len(out_of_coil) == 1
        assert out_of_coil[0]["target"]["node"] == "gen-ground"

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


class TestPowerZoneSingleOccurrence:
    """A+B+A-B- -- nenhum cilindro repete direção: 1 bobina Y por
    (cilindro, direção), 1 contato de potência cada."""

    def test_one_y_coil_per_cylinder_direction(self):
        data = sbe.generate(parse("A+B+A-B-"))
        y_coils = {n["id"]: n for n in data["nodes"] if n["type"] == "SolenoidCoil"}
        assert set(y_coils) == {"gen-ycoil-A-ext", "gen-ycoil-A-ret", "gen-ycoil-B-ext", "gen-ycoil-B-ret"}
        assert y_coils["gen-ycoil-A-ext"]["properties"]["sensor"]["coil"]["name"] == "YA1"
        assert y_coils["gen-ycoil-A-ret"]["properties"]["sensor"]["coil"]["name"] == "YA0"
        assert y_coils["gen-ycoil-B-ext"]["properties"]["sensor"]["coil"]["name"] == "YB1"
        assert y_coils["gen-ycoil-B-ret"]["properties"]["sensor"]["coil"]["name"] == "YB0"
        for coil in y_coils.values():
            assert coil["domain"] == "electric"

    def test_one_power_contact_per_movement_referencing_correct_k(self):
        data = sbe.generate(parse("A+B+A-B-"))  # A+ =atom0(K1), B+=atom1(K2), A-=atom2(K3), B-=atom3(K4)
        expected = {
            "gen-contact-power-A-ext-0": "K1",
            "gen-contact-power-B-ext-1": "K2",
            "gen-contact-power-A-ret-2": "K3",
            "gen-contact-power-B-ret-3": "K4",
        }
        for cid, kname in expected.items():
            n = _node(data, cid)
            assert n["type"] == "RelaySwitch"
            assert n["properties"]["contact_type"] == "NO"
            assert n["properties"]["relay_sensor"] == kname

    def test_power_contact_wired_from_own_vsource_tap_to_y_coil(self):
        data = sbe.generate(parse("A+B+A-B-"))
        into_contact = _conns_to(data, "gen-contact-power-A-ext-0", "T")
        assert len(into_contact) == 1
        assert into_contact[0]["source"]["node"] == "gen-vsource"

        out_of_contact = _conns_from(data, "gen-contact-power-A-ext-0", "B")
        assert len(out_of_contact) == 1
        assert out_of_contact[0]["target"]["node"] == "gen-ycoil-A-ext"
        assert out_of_contact[0]["target"]["anchor"] == "T"

        out_of_coil = _conns_from(data, "gen-ycoil-A-ext", "B")
        assert len(out_of_coil) == 1
        assert out_of_coil[0]["target"]["node"] == "gen-ground"

    def test_v42_actuators_always_solenoid_reading_y_coil(self):
        data = sbe.generate(parse("A+B+A-B-"))
        v42_a = _node(data, "gen-v42-A")
        v42_b = _node(data, "gen-v42-B")
        assert v42_a["properties"]["actuators"]["left"] == {"type": "solenoid", "sensor_name": "YA1"}
        assert v42_a["properties"]["actuators"]["right"] == {"type": "solenoid", "sensor_name": "YA0"}
        assert v42_b["properties"]["actuators"]["left"] == {"type": "solenoid", "sensor_name": "YB1"}
        assert v42_b["properties"]["actuators"]["right"] == {"type": "solenoid", "sensor_name": "YB0"}

    def test_no_pilot_sig_or_or_valve_created(self):
        data = sbe.generate(parse("A+B+A-B-"))
        assert [n for n in data["nodes"] if n["type"] == "Valve_3_2_Ways"] == []
        assert [n for n in data["nodes"] if n["type"] == "OrValve"] == []

    def test_full_node_and_connection_counts(self):
        data = sbe.generate(parse("A+B+A-B-"))
        assert len(data["nodes"]) == 39
        assert len(data["connections"]) == 50


class TestPowerZoneMultiCycle:
    """A+B+A-A+B-A- -- A+ ocorre nos átomos 0 e 3 (K1, K4); A- ocorre nos
    átomos 2 e 5 (K3, K6). Multi-ciclo vira só mais um contato em paralelo
    -- sem sig, sem OrValve."""

    def test_two_power_contacts_in_parallel_for_repeated_direction(self):
        data = sbe.generate(parse("A+B+A-A+B-A-"))
        c0 = _node(data, "gen-contact-power-A-ext-0")
        c3 = _node(data, "gen-contact-power-A-ext-3")
        assert c0["properties"]["relay_sensor"] == "K1"
        assert c3["properties"]["relay_sensor"] == "K4"

        for cid in ("gen-contact-power-A-ext-0", "gen-contact-power-A-ext-3"):
            into_contact = _conns_to(data, cid, "T")
            assert len(into_contact) == 1 and into_contact[0]["source"]["node"] == "gen-vsource"
            out_of_contact = _conns_from(data, cid, "B")
            assert len(out_of_contact) == 1
            assert out_of_contact[0]["target"]["node"] == "gen-ycoil-A-ext"
            assert out_of_contact[0]["target"]["anchor"] == "T"

    def test_still_only_one_y_coil_for_the_repeated_movement(self):
        data = sbe.generate(parse("A+B+A-A+B-A-"))
        y_ext_a = [n for n in data["nodes"] if n["id"] == "gen-ycoil-A-ext"]
        assert len(y_ext_a) == 1

    def test_v42_actuator_still_solenoid_no_pneumatic_pilot(self):
        data = sbe.generate(parse("A+B+A-A+B-A-"))
        v42_a = _node(data, "gen-v42-A")
        assert v42_a["properties"]["actuators"]["left"] == {"type": "solenoid", "sensor_name": "YA1"}
        assert v42_a["properties"]["actuators"]["right"] == {"type": "solenoid", "sensor_name": "YA0"}

    def test_no_pilot_sig_or_or_valve_created(self):
        data = sbe.generate(parse("A+B+A-A+B-A-"))
        assert [n for n in data["nodes"] if n["type"] == "Valve_3_2_Ways"] == []
        assert [n for n in data["nodes"] if n["type"] == "OrValve"] == []

    def test_full_node_and_connection_counts(self):
        data = sbe.generate(parse("A+B+A-A+B-A-"))
        assert len(data["nodes"]) == 51
        assert len(data["connections"]) == 68


class TestPowerZoneParallelBlock:
    def test_full_node_and_connection_counts(self):
        data = sbe.generate(parse("C+(A+B+)C-A-B-"))
        assert len(data["nodes"]) == 53
        assert len(data["connections"]) == 68


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
