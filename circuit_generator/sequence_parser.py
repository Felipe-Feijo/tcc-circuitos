"""Parse e validação de sequências de atuação de cilindros pneumáticos.

Converte strings como "A+B-A-B+" em listas de tuplas (cilindro, direção)
e valida regras de alternância e fechamento de ciclo.
"""

import re


def parse(sequence: str) -> list[tuple[str, str]]:
    """
    "A+B+A-B-" → [("A","+"), ("B","+"), ("A","-"), ("B","-")]
    Lança ValueError se a string não contiver nenhum token válido
    ou se os cilindros violarem as regras de alternância de estado.
    """
    tokens = re.findall(r'([A-Z][a-z]*)([+-])', sequence)
    if not tokens:
        raise ValueError(f"Sequência inválida: {sequence!r}")
    validate_cylinder_states(tokens)
    return tokens


def validate_cylinder_states(events: list[tuple]) -> None:
    """
    Valida que cada cilindro:
      1. Nunca repete a mesma direção consecutivamente (ex: A+...A+ sem A- no meio).
      2. Fecha o ciclo: termina no estado oposto ao primeiro movimento
         (o primeiro movimento sai de um estado e o último deve retornar a ele).

    Aceita eventos de 2 ou 3 campos — (letra, direção) ou
    (letra, direção, parallel_id); o parallel_id é ignorado aqui.

    Lança ValueError com mensagem descritiva se alguma regra for violada.
    Não assume estado inicial — o cilindro pode começar retraído ou avançado.
    """
    first_move: dict[str, str] = {}   # direção do primeiro evento de cada cilindro
    last_move:  dict[str, str] = {}   # direção do último evento de cada cilindro

    for letter, direction, *_ in events:
        if letter not in first_move:
            first_move[letter] = direction
        else:
            prev = last_move[letter]
            if direction == prev:
                state_name = "estendido" if prev == "+" else "retraído"
                raise ValueError(
                    f"Cilindro '{letter}' tenta mover para '{direction}' estando já "
                    f"{state_name}. Movimentos consecutivos na mesma direção são inválidos."
                )
        last_move[letter] = direction

    # Para fechar o ciclo, o último movimento deve ser o oposto do primeiro.
    # Ex: primeiro="+", último deve ser "-" (voltou ao estado de origem).
    opposite = {"+": "-", "-": "+"}
    for letter in first_move:
        if last_move[letter] != opposite[first_move[letter]]:
            raise ValueError(
                f"Cilindro '{letter}' não fecha o ciclo: "
                f"primeiro movimento '{first_move[letter]}', último '{last_move[letter]}'. "
                f"A sequência deve retornar cada cilindro ao seu estado inicial."
            )


def extract_cylinders(events: list[tuple]) -> list[str]:
    """Retorna letras únicas na ordem de primeira aparição.

    Aceita eventos de 2 ou 3 campos (ver `validate_cylinder_states`).
    """
    seen: dict[str, bool] = {}
    for letter, *_ in events:
        seen.setdefault(letter, True)
    return list(seen.keys())


def split_into_groups(events: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    """
    Divide a sequência em grupos onde nenhuma letra se repete.
    Ex: [A+, B+, A-, B-] → [[A+, B+], [A-, B-]]
    Usado pelo método cascata.
    """
    groups: list[list] = []
    current: list = []
    seen: set[str] = set()
    for event in events:
        letter, _ = event
        if letter in seen:
            groups.append(current)
            current = [event]
            seen = {letter}
        else:
            current.append(event)
            seen.add(letter)
    if current:
        groups.append(current)
    return groups