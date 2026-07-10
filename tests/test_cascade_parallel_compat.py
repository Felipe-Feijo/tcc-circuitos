"""Compatibilidade: cascade.generate() não deve quebrar ao receber eventos
de uma sequência com grupos paralelos (parallel_id).

Histórico: este teste originalmente checava que uma sequência com
parênteses gerava a MESMA topologia que a versão sem parênteses, porque
até o sub-projeto de movimento simultâneo `parallel_id` era ignorado por
completo. Agora que `cascade.py` implementa a fiação paralela de verdade
(ver tests/test_cascade_parallel_movement.py para a cobertura completa),
uma sequência com bloco `(...)` gera legitimamente mais nós/conexões que a
equivalente sem parênteses (a AndValve que mescla os eventos do bloco) —
a igualdade de contagem não se aplica mais; o que este teste garante agora
é só que a geração não quebra e que a diferença é exatamente a esperada.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.methods import cascade
from circuit_generator.sequence_parser import parse


def test_generate_accepts_parenthesized_sequence_without_crash():
    data_flat  = cascade.generate(parse("A+B+A-B-"))
    data_paren = cascade.generate(parse("(A+B+)A-B-"))
    # (A+B+) gera 1 nó a mais que a versão sem parênteses (a AndValve que
    # mescla a confirmação de A e B antes de trocar de grupo) e 2 conexões
    # a mais (as entradas X/Y da AndValve).
    assert len(data_paren["nodes"]) == len(data_flat["nodes"]) + 1
    assert len(data_paren["connections"]) == len(data_flat["connections"]) + 2
