"""Parse e validação de sequências de atuação de cilindros pneumáticos.

Converte strings como "A+B-A-B+" em listas de tuplas
(cilindro, direção, parallel_id) e valida regras de alternância, fechamento
de ciclo e grupos simultâneos entre parênteses.
"""

import re

_EVENT_RE = re.compile(r'([A-Z][a-z]*)([+-])')


def parse(sequence: str) -> list[tuple[str, str, int | None]]:
    """
    "A+B+A-B-" -> [("A","+",None), ("B","+",None), ("A","-",None), ("B","-",None)]
    "(A+B+)C-" -> [("A","+",0), ("B","+",0), ("C","-",None)]

    `parallel_id` é None para eventos sequenciais, ou um inteiro
    compartilhado por todos os eventos de um mesmo bloco "(...)" (movimentos
    simultâneos). Um bloco com um único evento, ex. "(A+)", é equivalente a
    "A+" sem parênteses (parallel_id=None).

    Lança ValueError se a string não contiver nenhum token válido, se os
    parênteses estiverem desbalanceados ou aninhados, se um bloco repetir
    cilindro, ou se os cilindros violarem as regras de alternância de estado.
    """
    text = sequence.replace(" ", "")
    if not text:
        raise ValueError(f"Sequência inválida: {sequence!r}")

    events: list[tuple[str, str, int | None]] = []
    in_block = False
    block_id = -1
    block_events: list[tuple[str, str]] = []
    pos = 0
    n = len(text)

    while pos < n:
        ch = text[pos]

        if ch == '(':
            if in_block:
                raise ValueError(
                    f"Sequência inválida: parênteses aninhados não são "
                    f"permitidos em {sequence!r}"
                )
            in_block = True
            block_id += 1
            block_events = []
            pos += 1
            continue

        if ch == ')':
            if not in_block:
                raise ValueError(
                    f"Sequência inválida: ')' sem '(' correspondente em {sequence!r}"
                )
            letters = [letter for letter, _ in block_events]
            for letter in letters:
                if letters.count(letter) > 1:
                    raise ValueError(
                        f"Cilindro '{letter}' repetido dentro do mesmo grupo "
                        f"simultâneo em {sequence!r}"
                    )
            if len(block_events) == 1:
                letter, direction = block_events[0]
                events.append((letter, direction, None))
            else:
                for letter, direction in block_events:
                    events.append((letter, direction, block_id))
            in_block = False
            pos += 1
            continue

        match = _EVENT_RE.match(text, pos)
        if not match:
            raise ValueError(f"Sequência inválida: {sequence!r}")
        letter, direction = match.group(1), match.group(2)
        if in_block:
            block_events.append((letter, direction))
        else:
            events.append((letter, direction, None))
        pos = match.end()

    if in_block:
        raise ValueError(
            f"Sequência inválida: '(' sem ')' correspondente em {sequence!r}"
        )
    if not events:
        raise ValueError(f"Sequência inválida: {sequence!r}")

    validate_cylinder_states(events)
    return events


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


def split_into_groups(events: list[tuple]) -> list[list[tuple]]:
    """
    Divide a sequência em grupos onde nenhuma letra se repete.
    Ex: [A+, B+, A-, B-] -> [[A+, B+], [A-, B-]]
    Usado pelo método cascata.

    Eventos com o mesmo `parallel_id` (3º campo, quando presente) formam um
    bloco atômico: se qualquer letra do bloco já apareceu no grupo corrente,
    o corte de grupo acontece antes do bloco inteiro, nunca no meio dele.
    Eventos de 2 campos (sem parallel_id) são tratados como blocos de 1.
    """
    groups: list[list] = []
    current: list = []
    seen: set[str] = set()

    for atom in _atomize(events):
        letters = {event[0] for event in atom}
        if letters & seen:
            groups.append(current)
            current = list(atom)
            seen = set(letters)
        else:
            current.extend(atom)
            seen |= letters
    if current:
        groups.append(current)
    return groups


def _atomize(events: list[tuple]) -> list[list[tuple]]:
    """Agrupa eventos consecutivos que compartilham o mesmo parallel_id
    (3º campo) em blocos atômicos. Eventos sem parallel_id (2 campos, ou
    3º campo None) viram blocos de 1 evento."""
    atoms: list[list[tuple]] = []
    i, n = 0, len(events)
    while i < n:
        pid = events[i][2] if len(events[i]) > 2 else None
        if pid is None:
            atoms.append([events[i]])
            i += 1
            continue
        j = i
        block: list[tuple] = []
        while j < n and (events[j][2] if len(events[j]) > 2 else None) == pid:
            block.append(events[j])
            j += 1
        atoms.append(block)
        i = j
    return atoms