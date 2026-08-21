"""Parsing and validation of pneumatic cylinder actuation sequences.

Converts strings like "A+B-A-B+" into lists of
(cylinder, direction, parallel_id) tuples and validates alternation
rules, cycle closure and simultaneous groups within parentheses.
"""

import re

_EVENT_RE = re.compile(r'([A-Z][a-z]*)([+-])')


def parse(sequence: str) -> list[tuple[str, str, int | None]]:
    """
    "A+B+A-B-" -> [("A","+",None), ("B","+",None), ("A","-",None), ("B","-",None)]
    "(A+B+)C-" -> [("A","+",0), ("B","+",0), ("C","-",None)]

    `parallel_id` is None for sequential events, or an integer shared by
    every event of the same "(...)" block (simultaneous moves). A block
    with a single event, e.g. "(A+)", is equivalent to "A+" without
    parentheses (parallel_id=None).

    Raises ValueError if the string contains no valid token, if the
    parentheses are unbalanced or nested, if a block repeats a
    cylinder, or if the cylinders violate the state-alternation rules.
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
    Validates that each cylinder:
      1. Never repeats the same direction consecutively (e.g. A+...A+ with no A- in between).
      2. Closes the cycle: ends in the opposite state from its first move
         (the first move leaves one state and the last one must return to it).

    Accepts 2- or 3-field events -- (letter, direction) or
    (letter, direction, parallel_id); parallel_id is ignored here.

    Raises ValueError with a descriptive message if any rule is violated.
    Assumes no initial state -- the cylinder can start either retracted or extended.
    """
    first_move: dict[str, str] = {}   # each cylinder's first event's direction
    last_move:  dict[str, str] = {}   # each cylinder's last event's direction

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

    # To close the cycle, the last move must be the opposite of the first.
    # E.g. first="+", last must be "-" (returned to the starting state).
    opposite = {"+": "-", "-": "+"}
    for letter in first_move:
        if last_move[letter] != opposite[first_move[letter]]:
            raise ValueError(
                f"Cilindro '{letter}' não fecha o ciclo: "
                f"primeiro movimento '{first_move[letter]}', último '{last_move[letter]}'. "
                f"A sequência deve retornar cada cilindro ao seu estado inicial."
            )


def extract_cylinders(events: list[tuple]) -> list[str]:
    """Returns unique letters in order of first appearance.

    Accepts 2- or 3-field events (see `validate_cylinder_states`).
    """
    seen: dict[str, bool] = {}
    for letter, *_ in events:
        seen.setdefault(letter, True)
    return list(seen.keys())


def split_into_groups(events: list[tuple]) -> list[list[tuple]]:
    """
    Splits the sequence into groups where no letter repeats.
    E.g. [A+, B+, A-, B-] -> [[A+, B+], [A-, B-]]
    Used by the cascade method.

    Events sharing the same `parallel_id` (3rd field, when present) form
    an atomic block: if any letter in the block has already appeared in
    the current group, the group cut happens before the whole block,
    never in the middle of it. 2-field events (no parallel_id) are
    treated as blocks of 1.
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
    """Groups consecutive events sharing the same parallel_id (3rd
    field) into atomic blocks. Events with no parallel_id (2 fields, or
    a None 3rd field) become 1-event blocks."""
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