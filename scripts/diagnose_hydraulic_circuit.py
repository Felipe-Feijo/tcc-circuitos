"""Headless timing/flow-balance diagnostic for a saved circuit JSON.

Unlike tests/simulate_json.py (which hand-maintains a partial node-type
table that goes stale -- it doesn't know about PressureGauge or
JunctionNodeItem, for instance), this loads the circuit through the
exact same path the real app uses: deserialize_scene() +
EditorController.build_graph() -- so it never drifts from what the GUI
actually simulates. Needs PyQt6 (a QApplication, even though nothing is
shown) because NodeItem is a QGraphicsItem.

Reports, per simulation step: wall-clock time and the worst flow
imbalance across every pressure node (sum of every anchor.flow sharing
a pressure_var -- should be ~0 at a converged, physically valid state).
Built while chasing a real reported bug (external_force on a
DoubleActingCylinder corrupting ScaleManager's flow scale -- see
DoubleActingCylinder's removed flow_hint) and a real cold-start
performance issue (NfevScheduler, simulation/hydraulic/scale_context.py)
-- kept here so both can be re-checked against a real circuit whenever
the hydraulic solver changes, without re-deriving this harness from
scratch.

Usage:
    python scripts/diagnose_hydraulic_circuit.py tests/fixtures/simple_hidr.json
    python scripts/diagnose_hydraulic_circuit.py tests/fixtures/simple_hidr.json --p-set 4e5 --external-force 1.0 --steps 8
    python scripts/diagnose_hydraulic_circuit.py tests/fixtures/simple_hidr.json --dt 0.05 --steps 5 --quiet
"""

import argparse
import contextlib
import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_engine(json_path: str, p_set: float | None, external_force: float | None):
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841 -- keeps Qt alive

    from editor.editor_state import EditorState
    from editor.editor_controller import EditorController
    from graphics.scene import GraphicsScene
    from persistence.serializer import deserialize_scene
    from simulation.simulation_engine import SimulationEngine
    # Side effect: imports every NodeItem subclass module, registering
    # it in NodeItem.class_registry -- deserialize_scene() needs every
    # type used in the JSON to already be registered.
    from main_window.ui.registry.node_registry import _discover_palette_nodes
    _discover_palette_nodes()

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    if p_set is not None:
        for n in data["nodes"]:
            if n["type"] == "ReliefValve":
                n["properties"]["p_set"] = p_set

    if external_force is not None:
        for n in data["nodes"]:
            if n["type"] in ("DoubleActingCylinder", "SingleActingCylinder"):
                n["properties"]["external_force"] = external_force

    editor = EditorState()
    scene = GraphicsScene()
    deserialize_scene(data, scene, editor=editor)

    builder = EditorController(scene).build_graph()
    builder.raise_if_errors()

    return SimulationEngine(builder.nodes, builder.connections, max_iterations=200)


def _worst_flow_imbalance(engine) -> float:
    pvar_flows: dict[str, list[float]] = {}
    for node in engine.nodes.values():
        for anchor in node.anchors.values():
            if anchor.domain != "hydraulic":
                continue
            pvar = getattr(anchor, "pressure_var", None)
            if not pvar or not isinstance(anchor.flow, float):
                continue
            pvar_flows.setdefault(pvar, []).append(anchor.flow)
    return max((abs(sum(flows)) for flows in pvar_flows.values()), default=0.0)


def run(json_path: str, steps: int, dt: float, p_set: float | None,
        external_force: float | None, quiet: bool) -> None:
    engine = _load_engine(json_path, p_set, external_force)

    print(f"{json_path}  steps={steps} dt={dt}"
          + (f" p_set={p_set:.3e}" if p_set is not None else "")
          + (f" external_force={external_force}" if external_force is not None else ""))

    for step in range(steps):
        buf = io.StringIO()
        t0 = time.perf_counter()
        with contextlib.redirect_stdout(buf if quiet else sys.stdout):
            engine.run_until_stable(dt=dt)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        print(f"  step {step}: {elapsed_ms:9.2f} ms")

    print(f"  worst flow imbalance across all pressure nodes: {_worst_flow_imbalance(engine):.3e}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("json_path", help="Path to the circuit JSON (editor's save format)")
    parser.add_argument("--steps", type=int, default=5)
    parser.add_argument("--dt", type=float, default=0.05)
    parser.add_argument("--p-set", type=float, default=None,
                         help="Overrides every ReliefValve's p_set (Pa)")
    parser.add_argument("--external-force", type=float, default=None,
                         help="Overrides every cylinder's external_force (N)")
    parser.add_argument("--quiet", action="store_true",
                         help="Suppresses the solver's per-attempt prints, keeps the summary")
    args = parser.parse_args()

    run(args.json_path, args.steps, args.dt, args.p_set, args.external_force, args.quiet)


if __name__ == "__main__":
    main()
