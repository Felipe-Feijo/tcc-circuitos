"""Testes de topologia para o suporte a multi-ciclo (OrValve) em
cascade.py — ver
docs/superpowers/specs/2026-07-10-cascade-multi-cycle-or-valve-design.md
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.sequence_parser import parse
from circuit_generator.methods import cascade


def _conns_from(data, node_id, anchor=None):
    return [c for c in data["connections"]
            if c["source"]["node"] == node_id
            and (anchor is None or c["source"]["anchor"] == anchor)]


def _conns_to(data, node_id, anchor=None):
    return [c for c in data["connections"]
            if c["target"]["node"] == node_id
            and (anchor is None or c["target"]["anchor"] == anchor)]


class TestSingleCycleRegression:
    """Sequência sem repetição de cilindro: topologia deve ficar idêntica à
    versão anterior a este sub-projeto (contagens capturadas rodando o
    código atual antes desta mudança)."""

    def test_no_or_valve_created(self):
        data = cascade.generate(parse("A+B+A-B-"))
        assert [n for n in data["nodes"] if n["type"] == "OrValve"] == []

    def test_node_and_connection_counts_unchanged(self):
        data = cascade.generate(parse("A+B+A-B-"))
        assert len(data["nodes"]) == 24
        assert len(data["connections"]) == 29

    def test_v42_pl_fed_directly_from_bus_first_event(self):
        # A+ é o primeiro evento do grupo 0 -> v42-A.PL alimentado direto do
        # barramento, com a 4/2 como "source" da chamada (convenção
        # original, preservada quando há só 1 fonte)
        data = cascade.generate(parse("A+B+A-B-"))
        conns = _conns_from(data, "gen-v42-A", "PL")
        assert len(conns) == 1
        assert conns[0]["target"]["node"] == "gen-pl-grp1"

    def test_v42_b_pl_fed_by_chained_sig(self):
        # B+ é o segundo evento do grupo 0 -> v42-B.PL alimentado pelo sig
        # de A+ (encadeado); o id do sig agora inclui o índice do evento
        # (flat_idx=0 para o primeiro evento da sequência)
        data = cascade.generate(parse("A+B+A-B-"))
        conns = _conns_to(data, "gen-v42-B", "PL")
        assert len(conns) == 1
        assert conns[0]["source"]["node"] == "gen-sig-A-ext-0"
        assert conns[0]["source"]["anchor"] == "A"


class TestUniqueSignalValveIds:
    def test_no_duplicate_node_ids_for_repeated_cylinder(self):
        data = cascade.generate(parse("B+A+B-A-A+A-"))
        ids = [n["id"] for n in data["nodes"]]
        assert len(ids) == len(set(ids))


class TestTwoOccurrencesSamePilot:
    """Mesmo cilindro repete a mesma direção duas vezes, ambas as fontes
    vindas direto do barramento -> 1 OrValve por pilot afetado."""

    def test_exactly_one_or_valve_per_affected_pilot(self):
        data = cascade.generate(parse("A+B+A-B-A+A-"))
        or_nodes = [n for n in data["nodes"] if n["type"] == "OrValve"]
        roles = sorted(n.get("_role", "") for n in or_nodes)
        assert roles == ["or_valve:A:PL:0", "or_valve:A:PR:0"]

    def test_or_valve_pl_inputs_are_the_two_bus_triggers(self):
        data = cascade.generate(parse("A+B+A-B-A+A-"))
        or_pl = next(n for n in data["nodes"]
                     if n.get("_role") == "or_valve:A:PL:0")
        x_conn = _conns_to(data, or_pl["id"], "X")
        y_conn = _conns_to(data, or_pl["id"], "Y")
        assert len(x_conn) == 1 and len(y_conn) == 1
        assert x_conn[0]["source"]["node"] == "gen-pl-grp1"
        assert y_conn[0]["source"]["node"] == "gen-pl-grp3"

    def test_or_valve_output_feeds_v42_pilot(self):
        data = cascade.generate(parse("A+B+A-B-A+A-"))
        or_pl = next(n for n in data["nodes"]
                     if n.get("_role") == "or_valve:A:PL:0")
        out_conn = _conns_from(data, or_pl["id"], "A")
        assert len(out_conn) == 1
        assert out_conn[0]["target"]["node"] == "gen-v42-A"
        assert out_conn[0]["target"]["anchor"] == "PL"


class TestMixedTriggerSources:
    """Uma fonte de disparo pode vir do barramento (is_first_event) e a
    outra de uma sig encadeada (sig.A) — o merge via OR precisa aceitar as
    duas formas misturadas."""

    def test_or_valve_accepts_one_chained_and_one_bus_source(self):
        data = cascade.generate(parse("B+A+B-A-A+A-"))
        or_pl = next(n for n in data["nodes"]
                     if n.get("_role") == "or_valve:A:PL:0")
        x_conn = _conns_to(data, or_pl["id"], "X")
        y_conn = _conns_to(data, or_pl["id"], "Y")
        assert len(x_conn) == 1 and len(y_conn) == 1
        # primeira fonte (B+, encadeada) -> X; segunda (A+, direto do
        # barramento do grupo 2) -> Y
        assert x_conn[0]["source"]["node"] == "gen-sig-B-ext-0"
        assert x_conn[0]["source"]["anchor"] == "A"
        assert y_conn[0]["source"]["node"] == "gen-pl-grp3"


class TestThreeOccurrencesSamePilotChain:
    """3 ocorrências da mesma direção no mesmo cilindro -> cadeia de 2
    OrValve por pilot afetado (a OrValve só tem 2 entradas)."""

    def test_two_chained_or_valves_per_pilot(self):
        data = cascade.generate(parse("A+A-A+A-A+A-"))
        or_nodes = [n for n in data["nodes"] if n["type"] == "OrValve"]
        assert len(or_nodes) == 4  # 2 na cadeia do PL + 2 na cadeia do PR

    def test_second_or_in_chain_consumes_first_ors_output(self):
        data = cascade.generate(parse("A+A-A+A-A+A-"))
        or0 = next(n for n in data["nodes"] if n.get("_role") == "or_valve:A:PL:0")
        or1 = next(n for n in data["nodes"] if n.get("_role") == "or_valve:A:PL:1")
        or0_out = _conns_from(data, or0["id"], "A")
        assert len(or0_out) == 1
        assert or0_out[0]["target"]["node"] == or1["id"]

    def test_final_or_feeds_v42(self):
        data = cascade.generate(parse("A+A-A+A-A+A-"))
        or1 = next(n for n in data["nodes"] if n.get("_role") == "or_valve:A:PL:1")
        out_conn = _conns_from(data, or1["id"], "A")
        assert len(out_conn) == 1
        assert out_conn[0]["target"]["node"] == "gen-v42-A"
        assert out_conn[0]["target"]["anchor"] == "PL"
