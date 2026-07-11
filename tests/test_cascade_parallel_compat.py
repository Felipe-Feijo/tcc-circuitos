"""Compatibilidade: cascade.generate() não deve quebrar ao receber eventos
de uma sequência com grupos paralelos (parallel_id).

Histórico: este teste originalmente checava que uma sequência com
parênteses gerava a MESMA topologia que a versão sem parênteses, porque
até o sub-projeto de movimento simultâneo `parallel_id` era ignorado por
completo. Agora que `cascade.py` implementa a fiação paralela de verdade
(ver tests/test_cascade_parallel_movement.py para a cobertura completa),
uma sequência com bloco `(...)` gera uma topologia diferente (serial chaining
de signal valves em vez de AndValve). Com a troca de AndValve para serial
confirmation, a contagem de nós e conexões é exatamente a mesma — a serial
chain não adiciona nós extra. O que este teste garante agora é só que a
geração não quebra e que ambas as sequências têm a mesma contagem (nenhum
nó extra adicionado pela serial confirmation).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.methods import cascade
from circuit_generator.sequence_parser import parse


def test_generate_accepts_parenthesized_sequence_without_crash():
    data_flat  = cascade.generate(parse("A+B+A-B-"))
    data_paren = cascade.generate(parse("(A+B+)A-B-"))
    # Com serial confirmation (sem AndValve extra), ambas as sequências
    # (com e sem parênteses) têm a mesma topologia em termos de contagem de
    # nós e conexões — a serial chain não adiciona nós extras, apenas
    # reencadeia as conexões P dos signal valves.
    assert len(data_paren["nodes"]) == len(data_flat["nodes"])
    assert len(data_paren["connections"]) == len(data_flat["connections"])
