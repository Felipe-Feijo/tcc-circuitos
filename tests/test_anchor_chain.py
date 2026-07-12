import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.nodes.anchor_chain import real_anchor_chain


def test_empty_and_single_item_return_no_pairs():
    assert real_anchor_chain([], lambda x: True) == []
    assert real_anchor_chain(["a"], lambda x: True) == []


def test_two_items_always_paired_even_if_neither_is_real():
    assert real_anchor_chain(["a", "b"], lambda x: False) == [("a", "b")]


def test_no_real_middle_items_chains_only_endpoints():
    items = ["a", "b", "c", "d", "e"]
    assert real_anchor_chain(items, lambda x: False) == [("a", "e")]


def test_real_middle_items_split_the_chain():
    items = ["a", "b", "c", "d", "e", "f"]
    real = {"c"}
    assert real_anchor_chain(items, lambda x: x in real) == [
        ("a", "c"), ("c", "f"),
    ]


def test_all_items_real_matches_original_adjacent_chaining():
    items = ["a", "b", "c", "d"]
    assert real_anchor_chain(items, lambda x: True) == [
        ("a", "b"), ("b", "c"), ("c", "d"),
    ]


def test_real_item_adjacent_to_endpoint_does_not_duplicate_pair():
    items = ["a", "b", "c"]
    real = {"b"}
    assert real_anchor_chain(items, lambda x: x in real) == [
        ("a", "b"), ("b", "c"),
    ]
