"""Cadeia de anchors reais — usado para podar anchors intermediários de
PressureLine tanto no grafo de simulação quanto na criação de ConnectionItems.
"""

from typing import Callable


def real_anchor_chain(items: list, is_real: Callable[[object], bool]) -> list[tuple]:
    """Retorna os pares consecutivos entre os itens "reais" de uma lista ordenada.

    O primeiro e o último item da lista são sempre tratados como reais,
    independente de `is_real`, para manter a cadeia estruturalmente íntegra.

    Args:
        items: sequência ordenada de anchors.
        is_real: predicado item -> bool, avaliado nos itens do meio.

    Returns:
        Lista de tuplas (item_a, item_b) entre reais consecutivos, na ordem
        original. Lista vazia se items tiver menos de 2 elementos.
    """
    if len(items) < 2:
        return []

    reals = [items[0]]
    for item in items[1:-1]:
        if is_real(item):
            reals.append(item)
    reals.append(items[-1])

    return [(reals[i], reals[i + 1]) for i in range(len(reals) - 1)]
