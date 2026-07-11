"""Testes de topologia para o suporte a movimento simultâneo (AndValve) em
cascade.py — ver
docs/superpowers/specs/2026-07-10-cascade-parallel-movement-design.md
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.sequence_parser import parse
from circuit_generator.methods import cascade
from circuit_generator.methods.cascade import _atomize_group


class TestAtomizeGroup:
    def test_no_parallel_ids_each_event_is_its_own_atom(self):
        group = [("A", "+", None), ("B", "+", None)]
        assert _atomize_group(group) == [
            [(0, "A", "+")],
            [(1, "B", "+")],
        ]

    def test_two_tuples_without_parallel_id_field(self):
        # split_into_groups pode devolver 2-tuplas quando chamado direto
        # (fora de parse()) -- _atomize_group precisa tolerar isso.
        group = [("A", "+"), ("B", "+")]
        assert _atomize_group(group) == [
            [(0, "A", "+")],
            [(1, "B", "+")],
        ]

    def test_single_block_is_one_atom(self):
        group = [("A", "+", 0), ("B", "+", 0)]
        assert _atomize_group(group) == [
            [(0, "A", "+"), (1, "B", "+")],
        ]

    def test_event_then_block(self):
        group = [("C", "+", None), ("A", "+", 0), ("B", "+", 0)]
        assert _atomize_group(group) == [
            [(0, "C", "+")],
            [(1, "A", "+"), (2, "B", "+")],
        ]

    def test_two_blocks_in_sequence(self):
        group = [("A", "+", 0), ("B", "+", 0), ("C", "+", 1), ("D", "+", 1)]
        assert _atomize_group(group) == [
            [(0, "A", "+"), (1, "B", "+")],
            [(2, "C", "+"), (3, "D", "+")],
        ]

    def test_block_then_event_then_block(self):
        group = [
            ("A", "+", 0), ("B", "+", 0),
            ("C", "+", None),
            ("D", "+", 1), ("E", "+", 1),
        ]
        assert _atomize_group(group) == [
            [(0, "A", "+"), (1, "B", "+")],
            [(2, "C", "+")],
            [(3, "D", "+"), (4, "E", "+")],
        ]


def _conns_from(data, node_id, anchor=None):
    return [c for c in data["connections"]
            if c["source"]["node"] == node_id
            and (anchor is None or c["source"]["anchor"] == anchor)]


def _conns_to(data, node_id, anchor=None):
    return [c for c in data["connections"]
            if c["target"]["node"] == node_id
            and (anchor is None or c["target"]["anchor"] == anchor)]


class TestRegressionNoParallelBlocks:
    """Sequência sem parênteses: topologia deve ficar idêntica à versão
    anterior a este sub-projeto (contagens/ids capturados rodando o código
    atual antes desta mudança)."""

    def test_no_and_valve_created(self):
        data = cascade.generate(parse("A+B+A-B-"))
        assert [n for n in data["nodes"] if n["type"] == "AndValve"] == []

    def test_node_and_connection_counts_unchanged(self):
        data = cascade.generate(parse("A+B+A-B-"))
        assert len(data["nodes"]) == 24
        assert len(data["connections"]) == 29

    def test_signal_valve_ids_have_no_confirmation_suffix(self):
        data = cascade.generate(parse("A+B+A-B-"))
        ids = {n["id"] for n in data["nodes"] if n["type"] == "Valve_3_2_Ways"
               and n.get("_role", "").startswith("signal_valve:")}
        assert ids == {
            "gen-sig-A-ext-0", "gen-sig-B-ext-1",
            "gen-sig-A-ret-2", "gen-sig-B-ret-3",
        }

    def test_chained_trigger_unchanged(self):
        data = cascade.generate(parse("A+B+A-B-"))
        conns = _conns_to(data, "gen-v42-B", "PL")
        assert len(conns) == 1
        assert conns[0]["source"]["node"] == "gen-sig-A-ext-0"


class TestBlockStartsGroup:
    """"(A+B+)A-B-": o bloco é o único átomo do grupo 0 -- A e B disparados
    direto do barramento (sem duplicação de válvula, fan_out=1 para a
    confirmação, já que o bloco é ao mesmo tempo o primeiro e o último
    átomo do grupo), confirmação em série (sem AndValve): a sig de A puxa
    P do barramento, a sig de B puxa P da saída de A."""

    def test_no_and_valve_for_this_block(self):
        data = cascade.generate(parse("(A+B+)A-B-"))
        assert [n for n in data["nodes"] if n["type"] == "AndValve"] == []

    def test_a_and_b_triggered_directly_from_bus_no_duplication(self):
        data = cascade.generate(parse("(A+B+)A-B-"))
        a_pl = _conns_from(data, "gen-v42-A", "PL")
        b_pl = _conns_from(data, "gen-v42-B", "PL")
        assert len(a_pl) == 1 and a_pl[0]["target"]["node"] == "gen-pl-grp1"
        assert len(b_pl) == 1 and b_pl[0]["target"]["node"] == "gen-pl-grp1"

    def test_confirmation_is_a_serial_chain_a_then_b(self):
        data = cascade.generate(parse("(A+B+)A-B-"))
        a_out = _conns_from(data, "gen-sig-A-ext-0", "A")
        assert len(a_out) == 1
        assert a_out[0]["target"]["node"] == "gen-sig-B-ext-1"
        assert a_out[0]["target"]["anchor"] == "P"
        b_out = _conns_from(data, "gen-sig-B-ext-1", "A")
        assert len(b_out) == 1
        assert b_out[0]["target"]["node"] == "gen-mc-0"
        assert b_out[0]["target"]["anchor"] == "PR"

    def test_no_signal_valve_duplication_for_this_block(self):
        data = cascade.generate(parse("(A+B+)A-B-"))
        ids = {n["id"] for n in data["nodes"] if n["type"] == "Valve_3_2_Ways"
               and n.get("_role", "").startswith("signal_valve:")
               and n["id"].startswith(("gen-sig-A-ext", "gen-sig-B-ext"))}
        assert ids == {"gen-sig-A-ext-0", "gen-sig-B-ext-1"}


class TestSingleEventBeforeBlock:
    """"C+(A+B+)C-A-B-": C precede o bloco (A+B+) no mesmo grupo -- C
    precisa de 2 conjuntos de confirmação (fan_out=2, tamanho do próximo
    átomo), mas seu PILOT é disparado uma única vez."""

    def test_c_pilot_triggered_exactly_once(self):
        data = cascade.generate(parse("C+(A+B+)C-A-B-"))
        conns = _conns_from(data, "gen-v42-C", "PL")
        assert len(conns) == 1
        assert conns[0]["target"]["node"] == "gen-pl-grp1"

    def test_c_signal_valve_duplicated_into_two_confirmation_sets(self):
        data = cascade.generate(parse("C+(A+B+)C-A-B-"))
        ids = {n["id"] for n in data["nodes"]
               if n["type"] == "Valve_3_2_Ways"
               and n["id"].startswith("gen-sig-C-ext")}
        assert ids == {"gen-sig-C-ext-0-0", "gen-sig-C-ext-0-1"}

    def test_each_c_copy_triggers_a_different_block_event(self):
        data = cascade.generate(parse("C+(A+B+)C-A-B-"))
        a_pl = _conns_to(data, "gen-v42-A", "PL")
        b_pl = _conns_to(data, "gen-v42-B", "PL")
        assert a_pl[0]["source"]["node"] == "gen-sig-C-ext-0-0"
        assert b_pl[0]["source"]["node"] == "gen-sig-C-ext-0-1"

    def test_a_and_b_get_a_single_signal_valve_each(self):
        data = cascade.generate(parse("C+(A+B+)C-A-B-"))
        ids = {n["id"] for n in data["nodes"] if n["type"] == "Valve_3_2_Ways"
               and (n["id"].startswith("gen-sig-A-ext")
                    or n["id"].startswith("gen-sig-B-ext"))}
        assert ids == {"gen-sig-A-ext-1", "gen-sig-B-ext-2"}


class TestChainedBlocks:
    """"(A+B+)(C+D+)A-B-C-D-": dois blocos adjacentes no mesmo grupo -- o
    primeiro precisa de 2 conjuntos de confirmação (fan_out=2, tamanho do
    segundo bloco), cada um encadeando A+B em série (sem AndValve), cada
    conjunto alimentando um evento do segundo bloco."""

    def test_a_and_b_each_get_two_signal_valves(self):
        data = cascade.generate(parse("(A+B+)(C+D+)A-B-C-D-"))
        a_ids = {n["id"] for n in data["nodes"] if n["id"].startswith("gen-sig-A-ext")}
        b_ids = {n["id"] for n in data["nodes"] if n["id"].startswith("gen-sig-B-ext")}
        assert a_ids == {"gen-sig-A-ext-0-0", "gen-sig-A-ext-0-1"}
        assert b_ids == {"gen-sig-B-ext-1-0", "gen-sig-B-ext-1-1"}

    def test_no_and_valve_anywhere(self):
        data = cascade.generate(parse("(A+B+)(C+D+)A-B-C-D-"))
        assert [n for n in data["nodes"] if n["type"] == "AndValve"] == []

    def test_two_independent_serial_chains_merge_first_block(self):
        data = cascade.generate(parse("(A+B+)(C+D+)A-B-C-D-"))
        chain0 = _conns_from(data, "gen-sig-A-ext-0-0", "A")
        chain1 = _conns_from(data, "gen-sig-A-ext-0-1", "A")
        assert chain0[0]["target"]["node"] == "gen-sig-B-ext-1-0"
        assert chain0[0]["target"]["anchor"] == "P"
        assert chain1[0]["target"]["node"] == "gen-sig-B-ext-1-1"
        assert chain1[0]["target"]["anchor"] == "P"

    def test_each_chain_triggers_a_different_second_block_event(self):
        data = cascade.generate(parse("(A+B+)(C+D+)A-B-C-D-"))
        c_pl = _conns_to(data, "gen-v42-C", "PL")
        d_pl = _conns_to(data, "gen-v42-D", "PL")
        assert c_pl[0]["source"]["node"] == "gen-sig-B-ext-1-0"
        assert d_pl[0]["source"]["node"] == "gen-sig-B-ext-1-1"

    def test_second_block_chain_closes_the_group(self):
        data = cascade.generate(parse("(A+B+)(C+D+)A-B-C-D-"))
        c_out = _conns_from(data, "gen-sig-C-ext-2", "A")
        assert c_out[0]["target"]["node"] == "gen-sig-D-ext-3"
        assert c_out[0]["target"]["anchor"] == "P"
        d_out = _conns_from(data, "gen-sig-D-ext-3", "A")
        assert d_out[0]["target"]["node"] == "gen-mc-0"
        assert d_out[0]["target"]["anchor"] == "PR"


class TestDuplicationDoesNotPropagateBeyondImmediateNeighbor:
    """"C+D+E+(A+B+)C-D-E-A-B-": só E (o vizinho imediato do bloco)
    duplica; C e D permanecem com uma única válvula de sinalização cada."""

    def test_only_e_is_duplicated(self):
        data = cascade.generate(parse("C+D+E+(A+B+)C-D-E-A-B-"))
        c_ids = {n["id"] for n in data["nodes"] if n["id"].startswith("gen-sig-C-ext")}
        d_ids = {n["id"] for n in data["nodes"] if n["id"].startswith("gen-sig-D-ext")}
        e_ids = {n["id"] for n in data["nodes"] if n["id"].startswith("gen-sig-E-ext")}
        assert c_ids == {"gen-sig-C-ext-0"}
        assert d_ids == {"gen-sig-D-ext-1"}
        assert e_ids == {"gen-sig-E-ext-2-0", "gen-sig-E-ext-2-1"}

    def test_d_triggers_e_pilot_exactly_once(self):
        data = cascade.generate(parse("C+D+E+(A+B+)C-D-E-A-B-"))
        conns = _conns_to(data, "gen-v42-E", "PL")
        assert len(conns) == 1
        assert conns[0]["source"]["node"] == "gen-sig-D-ext-1"

    def test_c_triggers_d_pilot_exactly_once(self):
        data = cascade.generate(parse("C+D+E+(A+B+)C-D-E-A-B-"))
        conns = _conns_to(data, "gen-v42-D", "PL")
        assert len(conns) == 1
        assert conns[0]["source"]["node"] == "gen-sig-C-ext-0"


class TestUniqueSignalValveIds:
    def test_no_duplicate_node_ids_with_parallel_blocks(self):
        data = cascade.generate(parse("C+(A+B+)C-A-B-"))
        ids = [n["id"] for n in data["nodes"]]
        assert len(ids) == len(set(ids))
