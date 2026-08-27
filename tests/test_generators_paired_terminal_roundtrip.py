"""End-to-end regression test: generated circuits load through the REAL
graphics node classes (NodeItem.from_dict / ConnectionItem.from_dict) --
see docs/superpowers/sdd/2026-08-21-generators-paired-terminal-migration/.

This is the concrete regression the paired-terminal migration exists to
fix: before the migration, a generated PressureLine/Ground/VoltageSource
with more than one tap stored an N-anchor list in properties["anchors"],
which the current node classes don't understand (a KeyError was raised
by persistence/serializer.py when loading such a node). This test
exercises circuit_generator.generate_and_load -- the same call path the
editor UI uses -- so it genuinely routes through deserialize_scene ->
NodeItem.from_dict / ConnectionItem.from_dict, not just the generators'
own raw dict output (already covered by Tasks 4-7's own tests).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene

app = QApplication.instance() or QApplication([])

import pytest

from circuit_generator.circuit_generator import generate_and_load
from graphics.items.base.nodes.node_item import NodeItem
from main_window.ui.registry.node_registry import _discover_palette_nodes

# NodeItem.class_registry (used by NodeItem.from_dict) is populated as a
# side effect of importing each node module -- __init_subclass__ registers
# the class the moment its module loads. In the real app this happens when
# main_window.ui.registry.node_registry.register_nodes() walks the palette
# at startup; here we call the same discovery step directly so from_dict
# can resolve every node type the generators emit.
_discover_palette_nodes()


class _FakeEditor:
    """Minimal stand-in for EditorState. deserialize_scene only assigns
    it to node.editor/conn.editor and generate_and_load only checks for
    an optional fit_scene() -- no other attribute is touched."""
    pass


@pytest.mark.parametrize("method,sub_type,sequence", [
    ("cascade", None, "A+B+A-B-"),
    ("step_by_step", "pneumatic", "A+B+A-B-"),
    ("step_by_step", "electric", "A+B+A-B-"),
])
def test_generated_circuit_loads_through_real_node_classes(method, sub_type, sequence):
    scene = QGraphicsScene()

    # Must not raise: this is the real deserialize_scene -> NodeItem.from_dict
    # / ConnectionItem.from_dict path (persistence/serializer.py), not a
    # reimplementation. Raises KeyError against the pre-migration
    # properties["anchors"] format.
    generate_and_load(sequence, method, sub_type, scene, _FakeEditor())

    nodes = [item for item in scene.items() if isinstance(item, NodeItem)]
    assert nodes, "generation produced no nodes"

    # No node is left holding the old anchor-list format.
    for node in nodes:
        assert "anchors" not in node.properties, (
            f"node {node.id!r} ({node.node_type}) still has properties['anchors']"
        )

    # At least one bus must have actually grown a multi-tap rail (a
    # JunctionNodeItem is only ever created for an INTERIOR tap -- see
    # rail.py's _materialize_bus). Without this, a future regression that
    # collapses every bus back down to a single tap (e.g. a broken
    # request_tap/assign_sorted call site) would silently keep this test
    # green, since a single-tap bus round-trips through from_dict just
    # fine too -- it just wouldn't be exercising the paired-terminal
    # migration's actual reason for existing.
    junctions = [n for n in nodes if n.node_type == "junction"]
    assert junctions, (
        f"no JunctionNodeItem produced for {sequence!r} ({method}/{sub_type}) -- "
        f"every bus regressed to a single tap"
    )
