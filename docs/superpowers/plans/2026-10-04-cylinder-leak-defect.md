# Cylinder Internal Leakage Defect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `set_defect {"leak": c}` on a hydraulic double/single-acting cylinder adds a laminar leakage path across the piston; `clear_defect` removes it.

**Architecture:** Both cylinder nodes adopt `DefectMixin` with `DEFECT_FIELDS = {"leak": "c_leak"}` (healthy `c_leak = 0.0`). A per-class `_piston_velocity(...)` helper becomes the single definition of piston velocity, used by `equations` (solver values) and by a public `piston_velocity` property (post-solve anchor values) that drives position integration and the graphics velocity label. `CylinderItem` declares the shared defect field.

**Tech Stack:** Python 3.14, PyQt6, scipy-based hydraulic solver, pytest.

**Spec:** `docs/superpowers/specs/2026-10-04-cylinder-leak-defect-design.md`

## Global Constraints

- Work on branch `feat/cylinder-leak-defect`; nothing goes to `main`.
- Run tests from the repo root with the venv Scripts on PATH:
  `PATH="$PWD/../venv/Scripts:$PATH" ../venv/Scripts/python.exe -m pytest <target> -q -p no:cacheprovider`
- Command key `"leak"`, attribute `c_leak`, unit m³/s/Pa, healthy value `0.0`.
- With `c_leak = 0` the equations must be algebraically identical to today's (existing cylinder tests are the regression guard).
- Label `"Internal leakage c_L (m³/s/Pa)"`, placeholder `"ex: 1e-12  (≈ 0.6 L/min @ 100 bar)"`, `min_value=None`, via `QCoreApplication.translate("CylinderItem", ...)`; pt_BR `"Vazamento interno c_L (m³/s/Pa)"`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Negative leak typed in the dialog (`min_value=None` lets it through) — node must clamp to 0, not leak "backwards". Pinned in Tasks 1 and 2 (`test_negative_leak_clamps_to_zero`).
2. Defect applied while the piston is parked at an end stop under pump pressure — the stop must hold (`v ≈ 0`, `x` unchanged) while `Q_A = Q_L` keeps flowing. Pinned in Task 1 (`test_leak_at_extended_stop_flows_but_piston_holds`).
3. Leak cleared mid-run — speed must return to the healthy value on the next step. Pinned in Task 1 (`test_clear_mid_run_restores_healthy_speed`).
4. Pneumatic cylinders receiving a stray `set_defect {"leak": ...}` — must be a no-op (no `c_leak` attribute, no crash). Pinned in Tasks 1 and 2 (`test_pneumatic_ignores_leak`).
5. Velocity label when the solver reports an error string in flow/pressure — must not crash (keep previous label). Pinned in Task 3 (`test_velocity_label_skips_error_strings`).

---

### Task 1: Double-acting cylinder leakage

**Files:**
- Modify: `simulation/nodes/cylinder/double_acting_cylinder.py`
- Test: `tests/test_double_acting_cylinder_leak_defect.py` (create)

**Interfaces:**
- Produces: `DoubleActingCylinder.c_leak: float` (hydraulic only), `DEFECT_FIELDS = {"leak": "c_leak"}`, `_piston_velocity(Q_a, P_a, P_b) -> float`, property `piston_velocity -> float | None` (None outside hydraulic or when anchor flow/pressure is an error string).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_double_acting_cylinder_leak_defect.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from simulation.connections import Connection
from simulation.nodes.cylinder.double_acting_cylinder import DoubleActingCylinder
from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
from simulation.nodes.relief_valve import ReliefValve
from simulation.nodes.reservoir import Reservoir
from simulation.simulation_engine import SimulationEngine

Q = 1e-4
C = 1e-11
P_SET = 5e6
PROPS = {"bore": 0.05, "rod_diameter": 0.02, "stroke": 0.2, "external_force": 5000.0}


def _anch(node, *names):
    for name in names:
        node.add_anchor(name, domain="hydraulic")
    return node


def _cyl():
    return _anch(DoubleActingCylinder("cyl", domain="hydraulic", properties=dict(PROPS)), "A", "B")


def test_fresh_cylinder_has_no_defect():
    cyl = _cyl()
    assert cyl.c_leak == 0.0
    assert cyl.defect_active is False


def test_set_and_clear_leak():
    cyl = _cyl()
    cyl.handle_command({"action": "set_defect", "leak": C})
    assert cyl.c_leak == pytest.approx(C)
    assert cyl.defect_active is True
    cyl.handle_command({"action": "clear_defect"})
    assert cyl.c_leak == 0.0
    assert cyl.defect_active is False


def test_negative_leak_clamps_to_zero():
    cyl = _cyl()
    cyl.handle_command({"action": "set_defect", "leak": -1e-11})
    assert cyl.c_leak == 0.0


def test_pneumatic_ignores_leak():
    cyl = DoubleActingCylinder("cyl", domain="pneumatic")
    cyl.handle_command({"action": "set_defect", "leak": C})
    assert not hasattr(cyl, "c_leak")
    assert cyl.piston_velocity is None


def test_piston_velocity_subtracts_leak():
    cyl = _cyl()
    cyl.c_leak = C
    cyl.anchors["A"].flow = Q
    cyl.anchors["A"].pressure = 3e6
    cyl.anchors["B"].pressure = 1e6
    assert cyl.piston_velocity == pytest.approx((Q - C * 2e6) / cyl.area_a)


def test_conservation_with_leak_is_satisfied_by_leaky_root():
    import numpy as np
    cyl = _cyl()
    cyl.c_leak = C
    cyl.x = 0.1
    cyl.anchors["A"].pressure_var = "P_A"
    cyl.anchors["B"].pressure_var = "P_B"
    idx = {cyl.flow_var_a: 0, cyl.flow_var_b: 1, "P_A": 2, "P_B": 3}
    P_a, P_b = 3e6, 1e6
    Q_l = C * (P_a - P_b)
    v = (Q - Q_l) / cyl.area_a
    Q_b = -(cyl.area_b * v + Q_l)
    _, eq_conservation = cyl.equations(np.array([Q, Q_b, P_a, P_b]), idx)
    assert abs(eq_conservation) < 1e-15


def _circuit():
    """Fixed pump -> A (relief valve on the same line), B -> tank."""
    pump = _anch(FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": Q}), "P", "S")
    cyl = _cyl()
    rv = _anch(ReliefValve("rv", domain="hydraulic", properties={"p_set": P_SET}), "P", "T")
    r1 = _anch(Reservoir("r1", domain="hydraulic", properties={"pressure": 0.0}), "T")
    r2 = _anch(Reservoir("r2", domain="hydraulic", properties={"pressure": 0.0}), "T")
    r3 = _anch(Reservoir("r3", domain="hydraulic", properties={"pressure": 0.0}), "T")
    conns = [
        Connection(pump.get_anchor("S"), r1.get_anchor("T")),
        Connection(pump.get_anchor("P"), cyl.get_anchor("A")),
        Connection(pump.get_anchor("P"), rv.get_anchor("P")),
        Connection(rv.get_anchor("T"), r2.get_anchor("T")),
        Connection(cyl.get_anchor("B"), r3.get_anchor("T")),
    ]
    nodes = {n.id: n for n in (pump, cyl, rv, r1, r2, r3)}
    return SimulationEngine(nodes, {c.id: c for c in conns}), cyl


def _expected_v(cyl):
    a, b = cyl.anchors["A"], cyl.anchors["B"]
    return (a.flow - cyl.c_leak * (a.pressure - b.pressure)) / cyl.area_a


def test_healthy_extension_speed_is_q_over_area():
    engine, cyl = _circuit()
    engine.run_until_stable(dt=0.1)
    assert cyl.piston_velocity == pytest.approx(Q / cyl.area_a, rel=1e-3)


def test_leak_slows_extension():
    engine, cyl = _circuit()
    cyl.handle_command({"action": "set_defect", "leak": C})
    x0 = cyl.x
    engine.run_until_stable(dt=0.1)
    v = cyl.piston_velocity
    assert v == pytest.approx(_expected_v(cyl), rel=1e-6)
    # P_A ~ F/A_A ~ 2.5 MPa -> Q_L ~ 2.5e-5, a quarter of the pump flow
    assert v < 0.85 * Q / cyl.area_a
    assert cyl.x - x0 == pytest.approx(v * 0.1, rel=1e-6)


def test_clear_mid_run_restores_healthy_speed():
    engine, cyl = _circuit()
    cyl.handle_command({"action": "set_defect", "leak": C})
    engine.run_until_stable(dt=0.1)
    cyl.handle_command({"action": "clear_defect"})
    engine.run_until_stable(dt=0.1)
    assert cyl.piston_velocity == pytest.approx(Q / cyl.area_a, rel=1e-3)


def test_leak_at_extended_stop_flows_but_piston_holds():
    engine, cyl = _circuit()
    cyl.handle_command({"action": "set_defect", "leak": C})
    for _ in range(100):
        engine.run_until_stable(dt=0.1)
        if cyl.x >= cyl.stroke:
            break
    assert cyl.x == pytest.approx(cyl.stroke)
    engine.run_until_stable(dt=0.1)
    engine.run_until_stable(dt=0.1)
    assert cyl.x == pytest.approx(cyl.stroke)
    assert abs(cyl.piston_velocity) < 1e-6
    # Pump pressure climbs to the relief setting; the leak keeps flowing.
    assert cyl.anchors["A"].pressure == pytest.approx(P_SET, rel=1e-2)
    assert cyl.anchors["A"].flow == pytest.approx(C * P_SET, rel=2e-2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PATH="$PWD/../venv/Scripts:$PATH" ../venv/Scripts/python.exe -m pytest tests/test_double_acting_cylinder_leak_defect.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: ... 'c_leak'` / `'piston_velocity'`, `defect_active` missing.

- [ ] **Step 3: Implement**

In `simulation/nodes/cylinder/double_acting_cylinder.py`:

Imports and class header:

```python
import math
from simulation.nodes.nodes import Node
from simulation.nodes.defect import DefectMixin
from simulation.hydraulic import HydraulicMixin

class DoubleActingCylinder(DefectMixin, Node, HydraulicMixin):
    # worn piston seal: laminar leakage A -> B, Q_L = c_leak * (P_A - P_B)
    DEFECT_FIELDS = {"leak": "c_leak"}

    def __init__(...):  # unchanged signature
```

In the `if self.domain == "hydraulic":` block of `__init__`, after `self.friction = 1e-3 ...`:

```python
            self.c_leak         = 0.0    # m3/s/Pa -- healthy seal; set by the "leak" defect
```

Add after `__init__` (before the "Hydraulic contract" banner):

```python
    def _on_defect_changed(self) -> None:
        if hasattr(self, "c_leak"):
            self.c_leak = max(0.0, self.c_leak)

    def _piston_velocity(self, Q_a, P_a, P_b):
        """Piston velocity: port-A flow minus what leaks across to B."""
        return (Q_a - self.c_leak * (P_a - P_b)) / self.area_a

    @property
    def piston_velocity(self):
        """Post-solve piston velocity (m/s), or None if unavailable."""
        if self.domain != "hydraulic":
            return None
        anchor_a = self.anchors.get("A")
        anchor_b = self.anchors.get("B")
        if anchor_a is None or anchor_b is None:
            return None
        values = (anchor_a.flow, anchor_a.pressure, anchor_b.pressure)
        if any(isinstance(v, str) for v in values):
            return None
        return self._piston_velocity(*values)
```

In `initial_guess`, replace the end-stop return:

```python
        if self.x <= EPS or self.x >= self.stroke - EPS:
            # Piston parked: only the leak (if any) crosses the ports.
            Q_l = self.c_leak * (P_a - P_b)
            return {self.flow_var_a: Q_l, self.flow_var_b: -Q_l}
```

In `equations`, replace from `v = Q_a / self.area_a` through `eq_conservation = ...`:

```python
        v       = self._piston_velocity(Q_a, P_a, P_b)
        F_hidro = P_a * self.area_a - P_b * self.area_b
        F_res   = self.external_force + self.friction * v
        F_net   = F_hidro - F_res

        F_scale = max(abs(F_hidro), abs(F_res), 1.0)
        Q_scale = max(self.area_a * self.stroke, 1e-8)

        f = F_net / F_scale
        # Complementarity acts on the piston's swept flow, not Q_a: at an
        # end stop the piston halts but Q_a = Q_leak can keep flowing.
        q = self.area_a * v / Q_scale

        EPS = self.stroke * 1e-4

        # Conservation per chamber, area-weighted (the rod makes area_b <
        # area_a): Q_a = area_a*v + Q_leak enters A, area_b*v + Q_leak
        # leaves B. With c_leak = 0 this is (area_b/area_a)*Q_a + Q_b = 0.
        eq_conservation = Q_b + self.area_b * v + self.c_leak * (P_a - P_b)
```

(The comments of the two end-stop branches that mention `Q_a` now refer to the piston: change "Forbidden: Q_a < 0" to "Forbidden: v < 0" and "Forbidden: Q_a > 0" to "Forbidden: v > 0".)

Replace `_integrate_hydraulic`:

```python
    def _integrate_hydraulic(self, dt):
        v = self.piston_velocity
        if v is None:
            return

        # unlocks if the piston reversed
        if self.locked_fwd and v < 0:
            self.locked_fwd = False
        if self.locked_bwd and v > 0:
            self.locked_bwd = False

        if not self.locked_fwd and not self.locked_bwd:
            self.x += v * dt
            self.x  = max(0.0, min(self.x, self.stroke))

            self.position = round(self.x / self.stroke) if self.stroke > 0 else 0

            if self.x >= self.stroke:
                self.locked_fwd = True
            if self.x <= 0.0:
                self.locked_bwd = True
```

- [ ] **Step 4: Run new tests and the existing cylinder tests**

Run: `PATH="$PWD/../venv/Scripts:$PATH" ../venv/Scripts/python.exe -m pytest tests/test_double_acting_cylinder_leak_defect.py tests/test_double_acting_cylinder_flow_conservation.py tests/test_double_acting_cylinder_flow_hint.py -q -p no:cacheprovider`
Expected: all PASS. If `test_leak_at_extended_stop_flows_but_piston_holds` fails on the pressure/flow asserts, print `cyl.anchors["A"].pressure`/`.flow` and check the relief valve is regulating (pump flow `Q` > `C*P_SET`), before touching tolerances.

- [ ] **Step 5: Run the full suite**

Run: `PATH="$PWD/../venv/Scripts:$PATH" ../venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add simulation/nodes/cylinder/double_acting_cylinder.py tests/test_double_acting_cylinder_leak_defect.py
git commit -m "feat: internal leakage defect for double-acting cylinder

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Single-acting cylinder leakage

**Files:**
- Modify: `simulation/nodes/cylinder/single_acting_cylinder.py`
- Test: `tests/test_single_acting_cylinder_leak_defect.py` (create)

**Interfaces:**
- Produces: `SingleActingCylinder.c_leak: float` (hydraulic only), `DEFECT_FIELDS = {"leak": "c_leak"}`, `_piston_velocity(Q, P_a) -> float`, property `piston_velocity -> float | None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_single_acting_cylinder_leak_defect.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from simulation.connections import Connection
from simulation.nodes.cylinder.single_acting_cylinder import SingleActingCylinder
from simulation.nodes.directional_valve.valve_2_2_ways import Valve_2_2_Ways
from simulation.nodes.reservoir import Reservoir
from simulation.simulation_engine import SimulationEngine

C = 1e-10
PROPS = {
    "bore": 0.05, "stroke": 0.2, "spring_k": 1000.0,
    "external_force": 500.0, "default_state": "extended",
}


def _anch(node, *names):
    for name in names:
        node.add_anchor(name, domain="hydraulic")
    return node


def _cyl():
    return _anch(SingleActingCylinder("sa", domain="hydraulic", properties=dict(PROPS)), "A")


def test_fresh_cylinder_has_no_defect():
    cyl = _cyl()
    assert cyl.c_leak == 0.0
    assert cyl.defect_active is False


def test_set_and_clear_leak():
    cyl = _cyl()
    cyl.handle_command({"action": "set_defect", "leak": C})
    assert cyl.c_leak == pytest.approx(C)
    assert cyl.defect_active is True
    cyl.handle_command({"action": "clear_defect"})
    assert cyl.c_leak == 0.0
    assert cyl.defect_active is False


def test_negative_leak_clamps_to_zero():
    cyl = _cyl()
    cyl.handle_command({"action": "set_defect", "leak": -C})
    assert cyl.c_leak == 0.0


def test_pneumatic_ignores_leak():
    cyl = SingleActingCylinder("sa", domain="pneumatic")
    cyl.handle_command({"action": "set_defect", "leak": C})
    assert not hasattr(cyl, "c_leak")
    assert cyl.piston_velocity is None


def test_piston_velocity_subtracts_leak():
    cyl = _cyl()
    cyl.c_leak = C
    cyl.anchors["A"].flow = 1e-5
    cyl.anchors["A"].pressure = 4e5
    assert cyl.piston_velocity == pytest.approx((1e-5 - C * 4e5) / cyl.area)


def test_extended_stop_bound_dropped_only_with_leak():
    cyl = _cyl()
    assert cyl.bounds == {cyl.flow_var: (None, 0.0)}
    cyl.c_leak = C
    assert cyl.bounds == {}


def _blocked_circuit():
    """Extended cylinder whose port A dead-ends at a closed 2/2 valve."""
    cyl = _cyl()
    valve = _anch(Valve_2_2_Ways("v", domain="hydraulic", properties={"k": 1e-7}), "P", "A")
    res = _anch(Reservoir("r", domain="hydraulic", properties={"pressure": 0.0}), "T")
    conns = [
        Connection(cyl.get_anchor("A"), valve.get_anchor("A")),
        Connection(valve.get_anchor("P"), res.get_anchor("T")),
    ]
    nodes = {n.id: n for n in (cyl, valve, res)}
    return SimulationEngine(nodes, {c.id: c for c in conns}), cyl


def test_healthy_blocked_cylinder_holds():
    engine, cyl = _blocked_circuit()
    for _ in range(5):
        engine.run_until_stable(dt=0.1)
    assert cyl.x == pytest.approx(cyl.stroke)


def test_leak_makes_blocked_cylinder_sink():
    engine, cyl = _blocked_circuit()
    cyl.handle_command({"action": "set_defect", "leak": C})
    xs = [cyl.x]
    for _ in range(5):
        engine.run_until_stable(dt=0.1)
        xs.append(cyl.x)
    assert all(b < a for a, b in zip(xs, xs[1:]))
    # Port blocked (Q = 0): v = -c * P_A / A, P_A held by spring + load.
    P_a = cyl.anchors["A"].pressure
    assert P_a == pytest.approx((cyl.spring_k * cyl.x + cyl.external_force) / cyl.area, rel=2e-2)
    assert cyl.piston_velocity == pytest.approx(-C * P_a / cyl.area, rel=2e-2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PATH="$PWD/../venv/Scripts:$PATH" ../venv/Scripts/python.exe -m pytest tests/test_single_acting_cylinder_leak_defect.py -q -p no:cacheprovider`
Expected: FAIL — `c_leak` / `piston_velocity` / `defect_active` missing.

- [ ] **Step 3: Implement**

In `simulation/nodes/cylinder/single_acting_cylinder.py`:

Imports and class header:

```python
from simulation.nodes.defect import DefectMixin
...
class SingleActingCylinder(DefectMixin, Node, HydraulicMixin):
    # worn piston seal: laminar leakage A -> vented spring chamber,
    # Q_L = c_leak * P_A
    DEFECT_FIELDS = {"leak": "c_leak"}
```

In the hydraulic block of `__init__`, after `self.friction = 1e-3 ...`:

```python
            self.c_leak          = 0.0    # m3/s/Pa -- healthy seal; set by the "leak" defect
```

Add after `__init__` (before the "End-stop helpers" banner):

```python
    def _on_defect_changed(self) -> None:
        if hasattr(self, "c_leak"):
            self.c_leak = max(0.0, self.c_leak)

    def _piston_velocity(self, Q, P_a):
        """Piston velocity: port flow minus what leaks to the vented side."""
        return (Q - self.c_leak * P_a) / self.area

    @property
    def piston_velocity(self):
        """Post-solve piston velocity (m/s), or None if unavailable."""
        if self.domain != "hydraulic":
            return None
        anchor = self.anchors.get("A")
        if anchor is None or isinstance(anchor.flow, str) or isinstance(anchor.pressure, str):
            return None
        return self._piston_velocity(anchor.flow, anchor.pressure)
```

In `initial_guess`, replace the end-stop return (keep the existing comment block above it, and add one line to it: "With a leak, the parked piston still passes Q = c_leak * P, estimated from p_hint for the same reason."):

```python
        if self.x <= EPS or self.x >= self.stroke - EPS:
            return {self.flow_var: self.c_leak * max(self.p_hint, 0.0)}
```

In `bounds`, replace the extended-stop branch:

```python
        elif self.x >= self.stroke - EPS:
            if self.c_leak > 0:
                # A pump holding pressure makes Q = c_leak * P > 0 with the
                # piston parked -- Q <= 0 would be infeasible. The stop is
                # still enforced by the complementarity on v in equations().
                return {}
            return {self.flow_var: (None, 0.0)}    # can only retract
```

In `equations`, replace `v = Q / self.area` with:

```python
        v = self._piston_velocity(Q, P)
```

and in the extended-stop branch replace `a = -Q / self.q_ref` with:

```python
            a = -self.area * v / self.q_ref        # >= 0 when the piston retracts
```

and in the retracted-stop branch replace `return [Q / (self.area * F_scale)]` with:

```python
            return [v / F_scale]  # forces the piston to stay -> v = 0
```

In `post_step_update`, replace the integration block:

```python
        if self.domain == "hydraulic" and dt is not None:
            v = self.piston_velocity
            if v is not None:
                self.x += v * dt
```

(keep the clamping and position lines that follow, re-indented under `if v is not None:`).

- [ ] **Step 4: Run new tests and related suites**

Run: `PATH="$PWD/../venv/Scripts:$PATH" ../venv/Scripts/python.exe -m pytest tests/test_single_acting_cylinder_leak_defect.py tests/test_frame_recorder.py -q -p no:cacheprovider`
Expected: all PASS.

- [ ] **Step 5: Run the full suite**

Run: `PATH="$PWD/../venv/Scripts:$PATH" ../venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add simulation/nodes/cylinder/single_acting_cylinder.py tests/test_single_acting_cylinder_leak_defect.py
git commit -m "feat: internal leakage defect for single-acting cylinder

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Cylinder defect dialog, velocity label, translations

**Files:**
- Modify: `graphics/items/base/nodes/cylinder/cylinder_item.py` (imports; `_update_velocity_from_domain` at ~206; new `defect_fields`)
- Modify: `resources/i18n/circuiteditor_pt_BR.ts`, `resources/i18n/circuiteditor_en.ts` (+ recompiled `.qm`)
- Test: `tests/test_cylinder_leak_defect_item.py` (create)

**Interfaces:**
- Consumes: `piston_velocity` property and `c_leak` / `DEFECT_FIELDS["leak"]` from Tasks 1–2.
- Produces: `CylinderItem.defect_fields() -> list[DefectFieldSpec]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cylinder_leak_defect_item.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from main_window.language import language_manager
from tests.defect_test_helpers import form_label_texts
from graphics.items.base.nodes.cylinder.double_acting_cylinder import (
    DoubleActingCylinder as DoubleItem,
)
from graphics.items.base.nodes.cylinder.single_acting_cylinder import (
    SingleActingCylinder as SingleItem,
)
from simulation.nodes.cylinder.double_acting_cylinder import DoubleActingCylinder

ITEMS = [DoubleItem, SingleItem]
LABEL = "Internal leakage c_L (m³/s/Pa)"


@pytest.mark.parametrize("cls", ITEMS)
def test_hydraulic_offers_one_leak_field(cls):
    specs = cls(domain="hydraulic").defect_fields()
    assert [s.key for s in specs] == ["leak"]
    assert specs[0].kind == "number"
    assert specs[0].min_value is None
    assert specs[0].label == LABEL
    assert specs[0].placeholder == "ex: 1e-12  (≈ 0.6 L/min @ 100 bar)"


@pytest.mark.parametrize("cls", ITEMS)
def test_pneumatic_offers_no_defect(cls):
    assert cls(domain="pneumatic").defect_fields() == []


def _node():
    node = DoubleActingCylinder(
        "cyl", domain="hydraulic",
        properties={"bore": 0.05, "rod_diameter": 0.02, "stroke": 0.2},
    )
    node.add_anchor("A", domain="hydraulic")
    node.add_anchor("B", domain="hydraulic")
    return node


def test_dialog_prefilled_from_live_node():
    item = DoubleItem(domain="hydraulic")
    node = _node()
    item.update_from_domain(node)
    node.handle_command({"action": "set_defect", "leak": 2e-12})
    dialog = item.build_defect_dialog()
    assert float(dialog.defect_widget("leak").text()) == 2e-12


def test_apply_emits_set_defect_float():
    item = DoubleItem(domain="hydraulic")
    item.update_from_domain(_node())
    dialog = item.build_defect_dialog()
    dialog.defect_widget("leak").setText("3e-12")
    received = []
    item.command.connect(lambda nid, payload: received.append(payload))
    item.apply_defect_from_dialog(dialog)
    assert received == [{"action": "set_defect", "leak": 3e-12}]


def test_label_translates_to_pt_br():
    item = SingleItem(domain="hydraulic")
    language_manager.apply_language(app, "pt_BR")
    try:
        dialog = item.build_defect_dialog()
        try:
            assert "Vazamento interno c_L (m³/s/Pa)" in form_label_texts(dialog)
        finally:
            dialog.close()
    finally:
        language_manager.apply_language(app, "en")


def test_velocity_label_uses_piston_velocity():
    item = DoubleItem(domain="hydraulic")
    node = _node()
    node.c_leak = 1e-11
    node.anchors["A"].flow = 1e-4
    node.anchors["A"].pressure = 3e6
    node.anchors["B"].pressure = 0.0
    shown = []
    item.update_velocity_label = shown.append
    item._update_velocity_from_domain(node)
    assert shown == [pytest.approx((1e-4 - 1e-11 * 3e6) / node.area_a)]


def test_velocity_label_skips_error_strings():
    item = DoubleItem(domain="hydraulic")
    node = _node()
    node.anchors["A"].flow = "ERR"
    shown = []
    item.update_velocity_label = shown.append
    item._update_velocity_from_domain(node)
    assert shown == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PATH="$PWD/../venv/Scripts:$PATH" ../venv/Scripts/python.exe -m pytest tests/test_cylinder_leak_defect_item.py -q -p no:cacheprovider`
Expected: FAIL — `defect_fields()` returns `[]`; velocity label still uses `flow / area`.

- [ ] **Step 3: Implement `defect_fields` and the velocity label**

In `graphics/items/base/nodes/cylinder/cylinder_item.py`, add the import after the `PropertiesDialog` import:

```python
from graphics.utils.defect_dialog import DefectFieldSpec
```

Replace the body of `_update_velocity_from_domain`:

```python
    def _update_velocity_from_domain(self, domain_node):
        """Shows the domain node's piston velocity (net of any internal leak)."""
        velocity = getattr(domain_node, "piston_velocity", None)
        if velocity is None:
            return
        if abs(velocity) < 1e-8:
            velocity = 0.0
        self.update_velocity_label(velocity)
```

Add, right before `build_properties_dialog`:

```python
    def defect_fields(self):
        # Explicit "CylinderItem" context, not self.tr(): inherited by
        # both cylinder subclasses (see build_properties_dialog's note).
        if self.domain != "hydraulic":
            return []
        return [DefectFieldSpec(
            "leak",
            QCoreApplication.translate("CylinderItem", "Internal leakage c_L (m³/s/Pa)"),
            "number",
            placeholder="ex: 1e-12  (≈ 0.6 L/min @ 100 bar)",
            # healthy is 0 and min_value is exclusive; the node clamps negatives
            min_value=None,
        )]
```

- [ ] **Step 4: Add the catalog entries and recompile**

In `resources/i18n/circuiteditor_pt_BR.ts`, right after the line `    <name>CylinderItem</name>`, insert (use the line number where `defect_fields`' `translate` call ended up):

```xml
    <message>
        <location filename="..\..\graphics\items\base\nodes\cylinder\cylinder_item.py" line="LINE" />
        <source>Internal leakage c_L (m³/s/Pa)</source>
        <translation>Vazamento interno c_L (m³/s/Pa)</translation>
    </message>
```

In `resources/i18n/circuiteditor_en.ts`, same place:

```xml
    <message>
        <location filename="..\..\graphics\items\base\nodes\cylinder\cylinder_item.py" line="LINE" />
        <source>Internal leakage c_L (m³/s/Pa)</source>
        <translation type="unfinished" />
    </message>
```

(`LINE` = the actual line number of the `QCoreApplication.translate("CylinderItem", "Internal leakage ...")` call — get it with `grep -n "Internal leakage" graphics/items/base/nodes/cylinder/cylinder_item.py`.)

Run: `PATH="$PWD/../venv/Scripts:$PATH" ../venv/Scripts/python.exe scripts/compile_translations.py`
Expected: both `.qm` files rewritten without errors.

- [ ] **Step 5: Run the tests**

Run: `PATH="$PWD/../venv/Scripts:$PATH" ../venv/Scripts/python.exe -m pytest tests/test_cylinder_leak_defect_item.py -q -p no:cacheprovider`
Expected: all PASS.

- [ ] **Step 6: Run the full suite**

Run: `PATH="$PWD/../venv/Scripts:$PATH" ../venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add graphics/items/base/nodes/cylinder/cylinder_item.py resources/i18n tests/test_cylinder_leak_defect_item.py
git commit -m "feat: leak defect dialog and leak-aware velocity label for cylinders

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
