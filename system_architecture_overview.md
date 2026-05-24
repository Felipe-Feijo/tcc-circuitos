# System Architecture Overview

This document describes the responsibilities and interactions between the main architectural layers of the simulator. It covers the editor, persistence, simulation, and automatic circuit generation subsystems.

---

## Layer Map

```
┌─────────────────────────────────────────────────────┐
│                    MainWindow                       │
│        (UI shell, menus, toolbars, dialogs)         │
└────────┬───────────────────────────┬────────────────┘
         │                           │
┌────────▼──────────────┐   ┌────────▼────────────────┐
│    Editor layer       │   │   Circuit Generator      │
│  GraphicsView/Scene   │   │  (sequence → JSON →      │
│  NodeItem/Connection  │   │   deserialize_scene)     │
│  EditorController     │   └─────────────────────────-┘
│  EditorState          │
│  Undo / Delete /      │
│  Clipboard managers   │
└────────┬──────────────┘
         │  serialize / deserialize
┌────────▼──────────────┐
│     Persistence       │
│  serializer.py        │
│  SceneFileSession     │
└────────┬──────────────┘
         │  GraphBuilder.build()
┌────────▼──────────────────────────────────────────┐
│                  Simulation layer                  │
│   SimulationSession                               │
│     ├── GraphBuilder   (scene → domain graph)     │
│     ├── SimulationEngine  (domain logic)          │
│     ├── StepScheduler  (timer / step queue)       │
│     ├── SimulationController  (step dispatch)     │
│     └── ViewSync       (domain state → graphics)  │
└───────────────────────────────────────────────────┘
```

---

## 1. MainWindow

**Role:** application shell and top-level orchestrator.

- Owns and initialises the Qt UI (menus, toolbars, palette, dialogs).
- Creates and wires together the Scene, GraphicsView, EditorState, and simulation objects.
- Routes high-level user actions (start/stop simulation, open/save file, generate circuit) to the appropriate subsystem.
- Contains no simulation logic and no domain knowledge.

---

## 2. Editor Layer

### 2.1 GraphicsScene / GraphicsView

**Role:** visual canvas and input router.

- `GraphicsScene` owns all `NodeItem`, `ConnectionItem`, `AnchorItem`, and `LabelItem` objects.
- `GraphicsView` handles viewport transformations, zoom, and pan.
- Neither class contains domain or simulation logic.

### 2.2 Graphics items

| Class | Responsibility |
|---|---|
| `NodeItem` | Renders a component sprite; owns its `AnchorItem` children; emits interaction signals. |
| `AnchorItem` | Represents a connection port; carries `exit_directions`, `domain`, and optional `margin`. |
| `ConnectionItem` | Renders an orthogonal wire between two anchors; manages waypoints. |
| `LabelItem` | Editable text label attached to a node. |

Graphics items are **read-only with respect to the domain** — simulation state is pushed *into* them by `ViewSync`; they never write back.

### 2.3 EditorState

**Role:** mutable interaction state shared across editor components.

Tracks the current `EditorMode` (select, connect, add node, …), the connection being drawn, and the active domain filter. Emits Qt signals when mode changes so that views and managers can react.

### 2.4 EditorController

**Role:** thin coordinator that builds the domain graph on demand.

Wraps `GraphBuilder` and exposes `build_graph()` to the rest of the application. Keeps no state of its own beyond a reference to the scene.

### 2.5 Editor managers

| Class | Responsibility |
|---|---|
| `UndoStack` / `SceneSnapshotCommand` | Scene-level undo/redo via JSON snapshots. |
| `DeleteManager` | Safe removal of nodes, connections and labels, deferred outside Qt event processing. |
| `ClipboardManager` | Copy/paste via JSON serialisation of the selected sub-graph. |

### 2.6 SensorRegistry

**Role:** centralised name registry for sensors and actuators in the scene.

Tracks every named component (cylinders, valves, coils, switches) and provides sequential name allocation (A1, A2, B1, …). Suppresses change signals during bulk load via a `loading()` context manager to avoid redundant updates.

---

## 3. Persistence

| Class / function | Responsibility |
|---|---|
| `serialize_scene` / `deserialize_scene` | Convert between `GraphicsScene` and a JSON-serialisable dict (format v1). |
| `save_to_file` / `load_from_file` | Thin wrappers that add file I/O around the serialiser. |
| `SceneFileSession` | Tracks the currently open file path and owns open/save/save-as dialogs. Updates the window title. |

The serialised format stores nodes (type, position, properties, labels) and connections (source anchor, target anchor, waypoints). Simulation state is never persisted.

---

## 4. Simulation Layer

### 4.1 SimulationSession

**Role:** lifecycle manager for a simulation run.

Coordinates startup and teardown: calls `GraphBuilder`, constructs `SimulationEngine`, wires up `StepScheduler`, `SimulationController`, and `ViewSync`, and puts `NodeItem`s into simulation mode. On stop, tears everything down and restores visual state.

### 4.2 GraphBuilder

**Role:** boundary object between UI and domain.

Reads the current scene, instantiates domain `Node` objects via `NODE_FACTORY`, and resolves anchors and connections into domain `Connection` objects. Produces a self-contained domain graph (`nodes: dict`, `connections: dict`) with no further references to the scene.

### 4.3 SimulationEngine

**Role:** core domain logic and state resolver.

Owns all domain `Node` and `Connection` objects. Executes simulation rules (pneumatic propagation, hydraulic solver, electrical logic) until a stable state is reached. Has no knowledge of Qt or graphics.

### 4.4 StepScheduler

**Role:** step queue and play/pause timer.

Queues step requests and dispatches them either immediately (manual step) or on a recurring `QTimer` (continuous play). Decouples timing from the engine.

### 4.5 SimulationController

**Role:** per-step dispatcher.

Receives a step request from `StepScheduler`, drives `SimulationEngine` through one simulation step, then calls `ViewSync` to push the resulting domain state to the graphics layer.

### 4.6 ViewSync

**Role:** domain-to-graphics bridge.

After each step, reads state from every domain `Node` and `Connection` and writes it to the corresponding `NodeItem` and `ConnectionItem` (colours, flow arrows, actuator positions). Maintains the `NodeItem → Node` and `ConnectionItem → Connection` mappings.

---

## 5. Circuit Generator

**Role:** automatic circuit synthesis from a textual actuation sequence.

Entry point: `generate_and_load(sequence, method, sub_type, scene, editor)`.

```
sequence string
    │
    ▼
sequence_parser.parse()        → list of cylinder events
    │
    ▼
methods/{cascade, step_by_step_pneumatic, step_by_step_electric}.generate()
                               → JSON dict (nodes + connections with _role tags)
    │
    ▼
layout_engine.apply()          → fills position.x/y, removes _role tags
    │
    ▼
deserialize_scene()            → loads result into the GraphicsScene
```

| Component | Responsibility |
|---|---|
| `sequence_parser` | Validates and tokenises the actuation sequence string. |
| `methods/` | Three generators (cascade, step-by-step pneumatic, step-by-step electric) that produce a circuit dict from a list of events. |
| `layout_engine` | Computes spatial positions for each node so wires route cleanly. |
| `astar_router` | Orthogonal A\* router used by the layout engine to calculate connection waypoints. |
| `SpriteMetrics` | Provides sprite dimensions and anchor offsets for layout calculations. |

The generator writes standard JSON that `deserialize_scene` can read, so it reuses the same persistence path as file load.

---

## 6. Domain Model

Simulation nodes live in `simulation/nodes/` and inherit from `Node` (base class in `simulation/nodes/nodes.py`). Hydraulic nodes additionally mix in `HydraulicMixin` which exposes the bond-graph interface used by the hydraulic solver.

```
Node (base)
├── DirectionalValve
│   ├── Valve_3_2_Ways  (+ HydraulicMixin)
│   ├── Valve_4_2_Ways
│   └── Valve_5_2_Ways
├── DoubleActingCylinder  (+ HydraulicMixin)
├── SingleActingCylinder  (+ HydraulicMixin)
├── FixedDisplacementPump (+ HydraulicMixin)
├── Reservoir             (+ HydraulicMixin)
├── DirectOperatedReliefValve (+ HydraulicMixin)
├── PressureLine
├── PressureSource / Exhaust
├── Coil / ButtonSwitch / RelaySwitch / RelayCoil
├── AndValve / OrValve
└── Ground / VoltageSource
```

The hydraulic solver (`simulation/hydraulic/solver.py`) implements a nonlinear system solver with convergence monitoring (`ConvergenceMonitor`) and adaptive step scaling (`ScaleManager`).

---

## 7. Data Flow Summary

**Edit → Simulate:**
```
User edits scene
    → EditorController.build_graph()
    → GraphBuilder produces domain graph
    → SimulationSession.start() constructs SimulationEngine
    → StepScheduler dispatches steps
    → SimulationController drives engine
    → ViewSync pushes state to graphics items
```

**Edit → Save:**
```
User saves
    → SceneFileSession.save()
    → serialize_scene() → JSON dict
    → written to .json file
```

**Load → Edit:**
```
User opens file
    → load_from_file()
    → deserialize_scene()
    → NodeItem.from_dict() / ConnectionItem.from_dict()
    → scene populated
```

**Generate → Edit:**
```
User enters sequence + method
    → generate_and_load()
    → parse → generate → layout → deserialize_scene()
    → scene populated (same path as file load)
```

---

## 8. Design Principles

- **Strict layer separation.** Graphics items never call simulation code. Simulation code never imports Qt.
- **Persistence as the common language.** The JSON scene format is the contract between the editor, the file system, and the circuit generator — all three converge on `deserialize_scene`.
- **Simulation is stateless between sessions.** `SimulationSession` builds everything from scratch on start and tears it down on stop; nothing persists across runs.
- **Undo at the editor level.** `SceneSnapshotCommand` snapshots the full scene JSON before each destructive operation, keeping undo simple and reliable.