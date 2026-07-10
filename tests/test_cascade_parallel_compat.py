"""Compatibilidade: cascade.generate() não deve quebrar ao receber eventos
de uma sequência com grupos paralelos (parallel_id), mesmo sem implementar
a fiação paralela ainda — isso é o próximo plano, não este.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.methods import cascade
from circuit_generator.sequence_parser import parse


def test_generate_accepts_parenthesized_sequence_without_crash():
    data_flat  = cascade.generate(parse("A+B+A-B-"))
    data_paren = cascade.generate(parse("(A+B+)A-B-"))
    assert len(data_paren["nodes"]) == len(data_flat["nodes"])
    assert len(data_paren["connections"]) == len(data_flat["connections"])
