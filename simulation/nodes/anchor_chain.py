"""Chain of real anchors -- used to prune intermediate PressureLine
anchors both in the simulation graph and when creating ConnectionItems.
"""

from typing import Callable


def real_anchor_chain(items: list, is_real: Callable[[object], bool]) -> list[tuple]:
    """Returns the consecutive pairs between the "real" items of an ordered list.

    The first and last items of the list are always treated as real,
    regardless of `is_real`, to keep the chain structurally intact.

    Args:
        items: ordered sequence of anchors.
        is_real: item -> bool predicate, evaluated on the middle items.

    Returns:
        List of (item_a, item_b) tuples between consecutive real items, in
        original order. Empty list if items has fewer than 2 elements.
    """
    if len(items) < 2:
        return []

    reals = [items[0]]
    for item in items[1:-1]:
        if is_real(item):
            reals.append(item)
    reals.append(items[-1])

    return [(reals[i], reals[i + 1]) for i in range(len(reals) - 1)]
