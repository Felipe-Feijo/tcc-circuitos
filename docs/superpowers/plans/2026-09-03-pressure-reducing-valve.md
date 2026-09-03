# Pressure Reducing Valve Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new hydraulic node type, the single-stage direct-acting pressure reducing valve, with a simulation node and a graphics/palette item.

**Architecture:** Two ports (`P` inlet, `A` outlet), no tank port. Modeled with the same Fischer-Burmeister complementarity technique already used by `ReliefValve`/`CheckValve`, but sensing the *outlet* pressure and throttling in series instead of shunting to tank. Graphics item follows the exact `ReliefValve` recipe (single static sprite, two fixed anchors, one required numeric property), registered automatically by `node_registry.py`.

**Tech Stack:** Python, PyQt6, numpy (solver), pytest.

**Spec:** `docs/superpowers/specs/2026-09-03-pressure-reducing-valve-design.md`

## Global Constraints

- Hydraulic domain only — no pneumatic behavior (spec Non-goals).
- No tank port, no reverse flow, no remote/pilot setpoint in this version (spec Non-goals) — `bounds` keep `Q_P >= 0` unconditionally.
- Port names are `P` (inlet) and `A` (outlet) — never `T` (spec: `T` is reserved for tank ports elsewhere in the codebase and would be misleading here).
- Sprite already exists at `resources/nodes/pressure_reducing_valve/pressure_reducing_valve.png` (200×162px) — do not recreate it.
- `ReliefValve` (`simulation/nodes/relief_valve.py`, `graphics/items/base/nodes/relief_valve.py`) is the direct precedent for both files in this plan — deviations from it must have a reason (see Task 2 note on `get_visual_state`).

---

## Deviation from the spec: no `get_visual_state()` override

The spec's Graphics item section mentions a cosmetic `"regulating"`/`"open"` visual state. Checking `ReliefValve` (the component this design explicitly mirrors) shows it does **not** override `get_visual_state()` despite having the same two physical regimes — and only one sprite file exists for `pressure_reducing_valve` (no `_regulating`/`_open` variants), so there is nothing for a dynamic state to switch between. Implementing it would be dead code. This plan skips it, matching what `ReliefValve` actually does rather than what an earlier design note assumed.

---

### Task 1: Simulation node

**Files:**
- Create: `simulation/nodes/pressure_reducing_valve.py`
- Test: `tests/test_pressure_reducing_valve_hydraulic.py`

**Interfaces:**
- Consumes: `simulation.nodes.nodes.Node` (constructor `Node.__init__(self, node_id, node_type, *, domain=None, properties=None, **kwargs)`, `self.anchors: dict`, `self.add_anchor(name, domain) -> Anchor`), `simulation.hydraulic.HydraulicMixin` (provides default `bounds`, `set_scale`, `flow_hint`, `p_hint`, `initial_guess`; base `p_ref`/`q_ref` class attributes).
- Produces: `PressureReducingValve` class in `simulation/nodes/pressure_reducing_valve.py`, constructor `PressureReducingValve(node_id: str, *, domain=None, properties=None, **kwargs)` requiring `properties["p_set"]` (float, Pa) when `domain == "hydraulic"`. Instance attributes `flow_var_p` (`f"Q_{id}_P"`), `flow_var_a` (`f"Q_{id}_A"`), `p_set` (float). Methods: `variables` (property), `bounds` (property), `hydraulic_ports()`, `equations(x, idx)`, `initial_guess` (property), `p_hint` (property), `update(outputs=None)`, `set_scale(p_ref, q_ref)`. `hydraulic_ports()` returns `{"P": flow_var_p, "A": flow_var_a}`. Later tasks (Task 2) import this class as `PressureReducingValveNode`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pressure_reducing_valve_hydraulic.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import math
import numpy as np

from simulation.nodes.pressure_reducing_valve import PressureReducingValve


def make_valve(p_set=1.5e7):
    valve = PressureReducingValve("prv", domain="hydraulic", properties={"p_set": p_set})
    valve.add_anchor("P", domain="hydraulic")
    valve.add_anchor("A", domain="hydraulic")
    valve.anchors["P"].pressure_var = "P_P"
    valve.anchors["A"].pressure_var = "P_A"
    return valve


def make_idx(valve):
    return {valve.flow_var_p: 0, valve.flow_var_a: 1, "P_P": 2, "P_A": 3}


# ---------------------------------------------------------------------------
# node_type / ports / variables / bounds
# ---------------------------------------------------------------------------

def test_node_type_is_pressure_reducing_valve():
    valve = make_valve()
    assert valve.type == "pressure_reducing_valve"


def test_hydraulic_ports_are_p_and_a():
    valve = make_valve()
    assert valve.hydraulic_ports() == {"P": valve.flow_var_p, "A": valve.flow_var_a}


def test_variables_include_flows_and_pressures():
    valve = make_valve()
    assert set(valve.variables) == {valve.flow_var_p, valve.flow_var_a, "P_P", "P_A"}


def test_bounds_restrict_to_forward_flow_only():
    valve = make_valve()
    assert valve.bounds == {
        valve.flow_var_p: (0.0, None),
        valve.flow_var_a: (None, 0.0),
    }


def test_p_hint_is_p_set():
    valve = make_valve(p_set=2e7)
    assert valve.p_hint == 2e7


def test_missing_p_set_raises_value_error():
    try:
        PressureReducingValve("prv2", domain="hydraulic", properties={})
        assert False, "expected ValueError for missing p_set"
    except ValueError as e:
        assert "p_set" in str(e)


# ---------------------------------------------------------------------------
# Regime 1: fully open (P_A == P_P), while P_A stays below p_set
# ---------------------------------------------------------------------------

def test_fully_open_regime_is_exact_root_below_p_set():
    valve = make_valve(p_set=1.5e7)
    idx = make_idx(valve)
    # P_P == P_A == 1e7, well below p_set -- no throttling needed.
    x = np.array([1e-4, -1e-4, 1.0e7, 1.0e7])
    eq_conservation, eq_fb = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_fb) < 1e-9


def test_fully_open_regime_breaks_once_p_a_would_exceed_p_set():
    """Sanity check that the fully-open assumption (P_A == P_P) stops being
    a root once that would push P_A above p_set -- confirms the FB equation
    actually gates the open regime instead of always returning 0."""
    valve = make_valve(p_set=1.5e7)
    idx = make_idx(valve)
    x = np.array([1e-4, -1e-4, 2e7, 2e7])  # P_P == P_A == 2e7 > p_set
    _, eq_fb = valve.equations(x, idx)
    assert abs(eq_fb) > 1e-6  # not a root -- violates a>=0 (p_set - P_A < 0)


# ---------------------------------------------------------------------------
# Regime 2: regulating (P_A held at p_set, P_P >= P_A)
# ---------------------------------------------------------------------------

def test_regulating_regime_is_exact_root_when_supply_exceeds_setpoint():
    valve = make_valve(p_set=1.5e7)
    idx = make_idx(valve)
    # P_A held at p_set, P_P above it -- valve throttling.
    x = np.array([1e-4, -1e-4, 2.0e7, 1.5e7])
    eq_conservation, eq_fb = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9
    assert abs(eq_fb) < 1e-9


def test_regulating_regime_not_a_root_if_p_a_drifts_from_setpoint():
    valve = make_valve(p_set=1.5e7)
    idx = make_idx(valve)
    # P_P above p_set (so b > 0), but P_A hasn't settled at p_set (a > 0 too)
    # -- both terms positive means neither complementarity slot is zero.
    x = np.array([1e-4, -1e-4, 2.0e7, 1.4e7])
    _, eq_fb = valve.equations(x, idx)
    assert abs(eq_fb) > 1e-6


# ---------------------------------------------------------------------------
# Conservation holds regardless of regime
# ---------------------------------------------------------------------------

def test_conservation_residual_scales_with_imbalance():
    valve = make_valve(p_set=1.5e7)
    idx = make_idx(valve)
    x = np.array([5e-4, -1e-4, 1.0e7, 1.0e7])  # Q_P + Q_A = 4e-4, not conserved
    eq_conservation, _ = valve.equations(x, idx)
    assert abs(eq_conservation - 4e-4 / valve.q_ref) < 1e-12


# ---------------------------------------------------------------------------
# initial_guess / set_scale
# ---------------------------------------------------------------------------

def test_initial_guess_seeds_zero_flow_and_p_anchor_pressure():
    valve = make_valve(p_set=1.5e7)
    valve.anchors["P"].pressure = 3e7
    guess = valve.initial_guess
    assert guess[valve.flow_var_p] == 0.0
    assert guess[valve.flow_var_a] == 0.0
    assert guess["P_P"] == 3e7


def test_set_scale_applies_minimum_floors():
    valve = make_valve()
    valve.set_scale(p_ref=10.0, q_ref=1e-15)
    assert valve.p_ref == 1e5   # floor: 1 bar
    assert valve.q_ref == 1e-10  # floor
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pressure_reducing_valve_hydraulic.py -v`
Expected: FAIL (or ERROR) — `ModuleNotFoundError: No module named 'simulation.nodes.pressure_reducing_valve'`.

- [ ] **Step 3: Implement the node**

Create `simulation/nodes/pressure_reducing_valve.py`:

```python
"""Single-stage, direct-acting pressure reducing valve simulation node.

Normally open -- throttles its own P->A passage to hold the OUTLET
pressure at p_set, and never boosts pressure. No tank port: unlike
ReliefValve (simulation/nodes/relief_valve.py), which shunts excess
flow to a T port when the INLET pressure exceeds its threshold, this
valve is in series and simply restricts its own orifice. Modeled with
the same Fischer-Burmeister smoothed complementarity ReliefValve and
CheckValve already use, mirrored to sense P_A (outlet) instead of P_in.
"""

import math
from simulation.nodes.nodes import Node
from simulation.hydraulic import HydraulicMixin


class PressureReducingValve(Node, HydraulicMixin):
    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "pressure_reducing_valve", domain=domain, properties=properties)
        if self.domain == "hydraulic":
            p_set = self.properties.get("p_set")
            if p_set is None:
                raise ValueError(f"PressureReducingValve '{self.id}': required property 'p_set' is not set.")
            self.p_set        = float(p_set)
            self.flow_var_p   = f"Q_{self.id}_P"
            self.flow_var_a   = f"Q_{self.id}_A"

    @property
    def p_hint(self) -> float:
        return self.p_set

    @property
    def variables(self) -> list:
        if self.domain != "hydraulic":
            return []
        vars_ = [self.flow_var_p, self.flow_var_a]
        for anchor_name in self.hydraulic_ports().keys():
            anchor = self.anchors.get(anchor_name)
            if anchor and anchor.pressure_var:
                vars_.append(anchor.pressure_var)
        return vars_

    @property
    def bounds(self):
        return {
            self.flow_var_p: (0.0, None),   # Q_P never negative -- forward flow only
            self.flow_var_a: (None, 0.0),   # Q_A never positive
        }

    def hydraulic_ports(self) -> dict:
        if self.domain != "hydraulic":
            return {}
        return {"P": self.flow_var_p, "A": self.flow_var_a}

    def equations(self, x, idx):
        Q_p = x[idx[self.flow_var_p]]
        Q_a = x[idx[self.flow_var_a]]
        P_p = x[idx[self.anchors["P"].pressure_var]]
        P_a = x[idx[self.anchors["A"].pressure_var]]

        Q_scale = self.q_ref
        P_scale = self.p_ref

        eq_conservation = (Q_p + Q_a) / Q_scale

        # a >= 0: P_A never exceeds p_set. b >= 0: the valve only drops
        # pressure (P_P >= P_A), never boosts it. Exactly one is zero:
        # either fully open (b=0, P_A=P_P) or regulating (a=0, P_A=p_set).
        a = (self.p_set - P_a) / P_scale
        b = (P_p - P_a) / P_scale
        eq_fb = a + b - math.sqrt(a * a + b * b)

        return [eq_conservation, eq_fb]

    @property
    def initial_guess(self) -> dict:
        if self.domain != "hydraulic":
            return {}
        anchor_p = self.anchors.get("P")
        p_hint = getattr(anchor_p, "pressure", 0.0) if anchor_p else 0.0
        if isinstance(p_hint, str):
            p_hint = 0.0
        return {
            self.flow_var_p: 0.0,
            self.flow_var_a: 0.0,
            self.anchors["P"].pressure_var: p_hint,
        }

    def update(self, outputs=None):
        pass  # no external state -- everything lives inside the solver

    def set_scale(self, p_ref: float, q_ref: float) -> None:
        self.p_ref = max(p_ref, 1e5)    # minimum 1 bar -- realistic scale
        self.q_ref = max(q_ref, 1e-10)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pressure_reducing_valve_hydraulic.py -v`
Expected: PASS — all tests green.

- [ ] **Step 5: Commit**

```bash
git add simulation/nodes/pressure_reducing_valve.py tests/test_pressure_reducing_valve_hydraulic.py
git commit -m "feat: add pressure reducing valve simulation node"
```

---

### Task 2: Graphics item

**Files:**
- Create: `graphics/items/base/nodes/pressure_reducing_valve.py`
- Test: `tests/test_pressure_reducing_valve_item.py`

**Interfaces:**
- Consumes: `PressureReducingValve` from `simulation.nodes.pressure_reducing_valve` (Task 1), `graphics.items.base.nodes.node_item.NodeItem` (base class; subclasses declare `node_type: str`, `simulation_cls: type`, implement `setup()`, may override `build_properties_dialog()`/`apply_properties_from_dialog()`; constructor accepts `domain=` kwarg), `graphics.items.base.nodes.node_descriptor.PaletteMeta` (`PaletteMeta(domains: tuple[str,...], sprite: str, name: str | None = None)`), `graphics.anchors.anchor.AnchorItem` (`AnchorItem(name: str, pos: QPointF, node=None, domain=None, exit_directions=None)`), `graphics.utils.properties_dialog.PropertiesDialog` (`add_number_field(label, placeholder="", value=None, required=False, min_value=None) -> QLineEdit`).
- Produces: `PressureReducingValve` class in `graphics/items/base/nodes/pressure_reducing_valve.py`, `node_type = "pressure_reducing_valve"`, `simulation_cls = PressureReducingValveNode` (imported as that alias, mirroring `graphics/items/base/nodes/relief_valve.py`'s `ReliefValveNode` alias). Auto-discovered by `main_window/ui/registry/node_registry.py` — no other file needs editing.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pressure_reducing_valve_item.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.pressure_reducing_valve import PressureReducingValve
from simulation.nodes.pressure_reducing_valve import PressureReducingValve as PressureReducingValveNode


def test_default_anchors_are_p_and_a_only():
    node = PressureReducingValve(domain="hydraulic")
    assert set(node.anchors.keys()) == {"P", "A"}


def test_p_and_a_positions_match_sprite():
    node = PressureReducingValve(domain="hydraulic")
    w, h = node.width, node.height
    assert (node.anchors["P"].pos().x(), node.anchors["P"].pos().y()) == (w * 98.5 / 200, 0)
    assert (node.anchors["A"].pos().x(), node.anchors["A"].pos().y()) == (w * 98.5 / 200, h)


def test_palette_meta():
    meta = PressureReducingValve.palette_meta()
    assert meta.domains == ("hydraulic",)
    assert meta.name == "Pressure Reducing Valve"
    assert meta.sprite.endswith("pressure_reducing_valve.png")


def test_simulation_cls_linkage():
    assert PressureReducingValve.simulation_cls is PressureReducingValveNode


def test_node_type():
    assert PressureReducingValve.node_type == "pressure_reducing_valve"


def test_build_properties_dialog_reflects_current_properties():
    node = PressureReducingValve(domain="hydraulic")
    node.properties["p_set"] = 1.5e7

    dialog = node.build_properties_dialog()

    assert dialog._field_p_set.text() == "15000000.0"


def test_apply_properties_from_dialog_updates_properties():
    node = PressureReducingValve(domain="hydraulic")
    dialog = node.build_properties_dialog()
    dialog._field_p_set.setText("2e7")

    node.apply_properties_from_dialog(dialog)

    assert node.properties["p_set"] == 2e7
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pressure_reducing_valve_item.py -v`
Expected: FAIL (or ERROR) — `ModuleNotFoundError: No module named 'graphics.items.base.nodes.pressure_reducing_valve'`.

- [ ] **Step 3: Implement the graphics item**

Create `graphics/items/base/nodes/pressure_reducing_valve.py`:

```python
"""Graphics node for the single-stage, direct-acting pressure reducing valve.

Sprite layout
-------------
Width x Height: 200 x 162 px
Anchor P (top)  : (width*98.5/200, 0)        inlet  -> top
Anchor A (base) : (width*98.5/200, height)   outlet -> bottom

Single static sprite -- unlike ReliefValve there is no pilot overlay
and no dynamic visual state (only one PNG exists for this component,
matching what ReliefValve itself does despite also having two physical
regimes: no get_visual_state() override).

Sprites
-------
pressure_reducing_valve.png -- body (ISO schematic, single stage).
"""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QCoreApplication
from simulation.nodes.pressure_reducing_valve import PressureReducingValve as PressureReducingValveNode

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.utils.properties_dialog import PropertiesDialog
from ....anchors.anchor import AnchorItem

_SPRITE_DIR = "resources/nodes/pressure_reducing_valve"


class PressureReducingValve(NodeItem):
    node_type = "pressure_reducing_valve"
    simulation_cls = PressureReducingValveNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("hydraulic",),
            sprite=f"{_SPRITE_DIR}/pressure_reducing_valve.png",
            name=QCoreApplication.translate("PressureReducingValve", "Pressure Reducing Valve"),
        )

    def setup(self) -> None:
        self.properties = {}
        self.pixmap = QPixmap(f"{_SPRITE_DIR}/pressure_reducing_valve.png")
        self.width  = self.pixmap.width()
        self.height = self.pixmap.height()

        self.add_anchor(AnchorItem("P", QPointF(self.width*98.5/200, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))
        self.add_anchor(AnchorItem("A", QPointF(self.width*98.5/200, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))

    def apply_properties(self) -> None:
        self.update()

    def build_properties_dialog(self):
        dialog = PropertiesDialog(title=self.tr("Pressure Reducing Valve — Properties"))
        dialog._field_p_set = dialog.add_number_field(
            self.tr("Setpoint pressure (Pa)"), placeholder="ex: 1.5e7  (= 150 bar)",
            value=self.properties.get("p_set"),
            required=True,
        )
        return dialog

    def apply_properties_from_dialog(self, dialog):
        p_set_text = dialog._field_p_set.text().strip()
        self.properties["p_set"] = float(p_set_text) if p_set_text else None
        self.update()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pressure_reducing_valve_item.py -v`
Expected: PASS — all tests green.

- [ ] **Step 5: Commit**

```bash
git add graphics/items/base/nodes/pressure_reducing_valve.py tests/test_pressure_reducing_valve_item.py
git commit -m "feat: add pressure reducing valve graphics/palette item"
```

---

### Task 3: Full test suite regression check

**Files:** none created/modified — verification only.

**Interfaces:** none.

- [ ] **Step 1: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS — no regressions in unrelated tests (palette discovery, node registry, translation catalog, etc. all pick up the new node automatically per `node_registry.py`'s auto-discovery).

- [ ] **Step 2: If green, no further action needed. If red, fix before considering the plan done.**

No commit for this task — it's a checkpoint, not a change.
