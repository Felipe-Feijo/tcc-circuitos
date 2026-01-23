# System Architecture Overview

This document explains the responsibilities and interactions between the main architectural components of the simulator:

* MainWindow
* GraphicsView / Scene (Editor layer)
* GraphBuilder
* SimulationEngine
* SimulationController

The goal is to clarify data flow, ownership, and control boundaries, both for maintenance and for academic evaluation.

---

## 1. MainWindow

**Role:** Application orchestrator and UI entry point.

### Responsibilities

* Owns and initializes the Qt UI (menus, toolbars, widgets).
* Creates and wires together the GraphicsView, Scene, and controllers.
* Handles high-level user actions (start simulation, stop simulation, reset, load/save).

### What MainWindow does *not* do

* It does **not** contain simulation logic.
* It does **not** understand domain concepts such as pressure or pistons.

MainWindow delegates all domain-related work to lower layers.

---

## 2. GraphicsView and Scene (Editor Layer)

**Role:** Visual editor and user interaction layer.

### Core elements

* `NodeItem`
* `AnchorItem`
* `ConnectionItem`

These are purely graphical objects derived from Qt graphics items.

### Responsibilities

* Render nodes, anchors, and connections.
* Handle mouse interaction (dragging, connecting, selecting).
* Emit UI events (e.g., button clicks on nodes).

### Design contract

* Graphics items **do not contain simulation logic**.
* Graphics items may expose IDs and names that allow mapping to domain objects.
* Graphics state (colors, animations, highlights) is updated *from* the simulation, never the opposite.

---

## 3. GraphBuilder

**Role:** Translator between the graphical editor and the domain graph.

GraphBuilder is the *boundary object* between UI and simulation.

### Responsibilities

* Read the current Scene state.
* Instantiate domain Nodes using `NODE_FACTORY`.
* Resolve anchors and connections into domain objects.
* Produce:

  * `nodes: dict[id, Node]`
  * `connections: dict[id, Connection]`

### Key properties

* Stateless after build: it does not persist references to the scene.
* Can be run multiple times to rebuild the domain graph from scratch.

### Why GraphBuilder exists

* Keeps SimulationEngine independent from Qt.
* Allows validation, debugging, and testing of the domain graph.

---

## 4. SimulationEngine

**Role:** Core domain logic and state resolver.

### Responsibilities

* Own all domain Nodes and Connections.
* Execute the simulation rules.
* Resolve pressure propagation until a stable state is reached.

### Key characteristics

* No knowledge of UI or graphics.
* Deterministic and synchronous.
* Operates only on domain objects (`Node`, `Anchor`, `Connection`).

### Control flow

* Called by SimulationController.
* Never calls UI code directly.

SimulationEngine is the *model* of the system.

---

## 5. SimulationController

**Role:** Bridge between simulation and visualization.

### Responsibilities

* Receive user commands from the UI (via signals).
* Invoke simulation steps on the SimulationEngine.
* Map domain state back to graphical items.

### Mapping responsibilities

* Maintains:

  * `NodeItem → DomainNode`
  * `ConnectionItem → DomainConnection`

### Update strategy

* After each simulation step:

  * Read domain state.
  * Apply visual updates (animations, colors, positions).

### Design contract

* SimulationController may *read* domain state.
* SimulationController may *write* graphical state.
* It must never mutate domain logic directly.

---

## 6. Overall Data Flow

```
User Action
    ↓
MainWindow
    ↓
Graphics Items (NodeItem / ConnectionItem)
    ↓
GraphBuilder (build once)
    ↓
SimulationEngine
    ↑
SimulationController
    ↑
Graphics Items (visual update)
```

---

## 7. Architectural Benefits

* Clear separation of concerns.
* UI can evolve independently from simulation rules.
* Simulation can be unit-tested without Qt.
* Undo/redo can be implemented at the editor or controller level.

---

## 8. Intended Extensions

* Undo/Redo: implemented at the editor level (Scene state snapshots or commands).
* Persistence: serialize Scene, not SimulationEngine.
* Multiple simulation modes: reuse SimulationEngine with different controllers.

---

This layered architecture intentionally mirrors classic MVC / hexagonal principles, adapted to a graphical, interactive simulation environment.
