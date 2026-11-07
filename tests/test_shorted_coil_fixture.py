"""Integration: tests/fixtures/bug_bobina_curto.json loaded the way the app
opens a file. K1 has both terminals on one point; K3 is in parallel with a
closed NC button contact. Neither may actuate, so both cylinders stay
retracted until the button opens the NC.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from main_window.ui.registry.node_registry import _discover_palette_nodes
from graphics.scene import GraphicsScene
from persistence.serializer import load_from_file
from editor.editor_controller import EditorController
from simulation.simulation_engine import SimulationEngine

# NodeItem.class_registry is filled as a side effect of importing each
# node module.
_discover_palette_nodes()

FIXTURE = Path(__file__).parent / "fixtures" / "bug_bobina_curto.json"


def _engine():
    scene = GraphicsScene()
    load_from_file(scene, str(FIXTURE), None)
    builder = EditorController(scene).build_graph()
    builder.raise_if_errors()
    return SimulationEngine(nodes=builder.nodes, connections=builder.connections)


def _position(engine, cyl_id):
    return engine.nodes[cyl_id].get_state()["position"]


def test_shorted_coils_do_not_actuate_and_cylinders_stay_retracted():
    engine = _engine()
    nodes = engine.nodes
    for _ in range(5):
        engine.run_until_stable(0.1)

    assert nodes["K1"].energized == 0
    assert nodes["K3"].energized == 0
    assert nodes["K2"].energized == 1  # correctly wired control coil
    assert nodes["Y1"].energized == 0
    assert nodes["Y2"].energized == 0
    assert _position(engine, "cyl-A") == 0
    assert _position(engine, "cyl-B") == 0

    # Wires painted only where current flows: around K1 and K3 they read
    # like dead-end branches, while the NC in parallel with K3 conducts.
    assert nodes["jA"].anchors["J"].state is True
    assert nodes["cNF"].anchors["T"].state is True
    assert nodes["cNF"].anchors["B"].state is True
    for coil in ("K1", "K3"):
        assert nodes[coil].anchors["T"].state is False, coil
        assert nodes[coil].anchors["B"].state is False, coil


def test_opening_the_nc_button_actuates_k3_and_advances_cylinder_b():
    engine = _engine()
    nodes = engine.nodes
    for _ in range(3):
        engine.run_until_stable(0.1)
    assert nodes["K3"].energized == 0

    nodes["cNF"].handle_command({"type": "switch", "value": 1})
    for _ in range(5):
        engine.run_until_stable(0.1)

    assert nodes["K3"].energized == 1
    assert nodes["K3"].anchors["T"].state is True
    assert nodes["K3"].anchors["B"].state is True
    assert nodes["K4"].energized == 1
    assert nodes["Y2"].energized == 1
    assert _position(engine, "cyl-B") == 1
    assert nodes["K1"].energized == 0
    assert _position(engine, "cyl-A") == 0
