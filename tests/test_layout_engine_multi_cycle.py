"""Teste de posicionamento end-to-end para o suporte a multi-ciclo — ver
docs/superpowers/specs/2026-07-10-cascade-multi-cycle-or-valve-design.md
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.sequence_parser import parse
from circuit_generator.methods import cascade
from circuit_generator.layout_engine import apply as apply_layout


def _positions_by_id(data):
    return {n["id"]: n["position"] for n in data["nodes"]}


def test_single_cycle_layout_still_works_end_to_end():
    # regressão: sequência de 1 ciclo continua funcionando sem OR nenhuma
    data = cascade.generate(parse("A+B+A-B-"))
    data = apply_layout(data)
    assert [n for n in data["nodes"] if n["type"] == "OrValve"] == []
    at_origin = [nid for nid, pos in _positions_by_id(data).items()
                 if pos["x"] == 0 and pos["y"] == 0]
    assert at_origin == []


def test_no_node_left_at_origin_for_multi_cycle_sequence():
    # "B+A+B-A-A+A-" produz uma OrValve com fonte mista (bus-direto + sig
    # encadeada), exercitando o fallback de posição das sigs "órfãs"
    data = cascade.generate(parse("B+A+B-A-A+A-"))
    data = apply_layout(data)
    at_origin = [nid for nid, pos in _positions_by_id(data).items()
                 if pos["x"] == 0 and pos["y"] == 0]
    assert at_origin == []


def test_or_valve_nodes_get_a_position():
    data = cascade.generate(parse("B+A+B-A-A+A-"))
    data = apply_layout(data)
    or_nodes = [n for n in data["nodes"] if n["type"] == "OrValve"]
    assert len(or_nodes) == 2
    for n in or_nodes:
        assert (n["position"]["x"], n["position"]["y"]) != (0, 0)


def test_orphan_signal_valves_get_a_position():
    # gen-sig-B-ext-0 e gen-sig-B-ret-2 alimentam uma OrValve, não a 4/2
    # diretamente — precisam do fallback de posição, não do KeyError antigo
    data = cascade.generate(parse("B+A+B-A-A+A-"))
    data = apply_layout(data)
    positions = _positions_by_id(data)
    for sig_id in ("gen-sig-B-ext-0", "gen-sig-B-ret-2"):
        assert sig_id in positions
        pos = positions[sig_id]
        assert (pos["x"], pos["y"]) != (0, 0)


def test_three_cycle_chain_layout_does_not_crash():
    # cadeia de 2 OrValve por pilot — garante que o caso N>2 também
    # atravessa o layout sem erro
    data = cascade.generate(parse("A+A-A+A-A+A-"))
    data = apply_layout(data)
    or_nodes = [n for n in data["nodes"] if n["type"] == "OrValve"]
    assert len(or_nodes) == 4
    at_origin = [nid for nid, pos in _positions_by_id(data).items()
                 if pos["x"] == 0 and pos["y"] == 0]
    assert at_origin == []
