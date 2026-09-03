# Pressure Reducing Valve Relief Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing pressure reducing valve with an optional `relieving` property that adds a `T` (tank) port, letting the valve actively hold its outlet at `p_set` via a `Reservoir` connection instead of only refusing more inflow.

**Architecture:** Extends the existing closed-regime branch (unchanged when `relieving=False`) with a parallel equation set active only when `relieving=True`: supply stays pinned shut (`Q_P=0`) and a new equation pulls the outlet back to `p_set` via the `T` port instead of leaving it floating. Same conditional-property pattern `ReliefValve.piloted` already uses (property → optional anchor → optional overlay sprite → optional dialog checkbox).

**Tech Stack:** Python, PyQt6, numpy (solver), pytest.

**Spec:** `docs/superpowers/specs/2026-09-03-pressure-reducing-valve-relief-port-design.md`

## Global Constraints

- `relieving=False` path must remain byte-for-byte behaviorally identical to what's already shipped — every existing test in both files must keep passing unmodified.
- `T`'s bounds are `(None, 0.0)` — flow only ever leaves through `T` (same convention as `ReliefValve`'s own `T` port).
- No implicit/internal reservoir: `T` is a real anchor the user must wire to a `Reservoir` node, exactly like every other tank port in this codebase (`simulation/nodes/reservoir.py` is what actually pins that pressure variable). Nothing in this plan should hardcode a fixed tank pressure inside the valve itself.
- Rejected approach (do not implement): a second, independent Fischer-Burmeister pair between `(P_A - p_set)` and `Q_T`. It's rank-deficient at `P_A = p_set` (both FB pairs satisfied by the same condition with nothing to decide which port supplies the correction). Use the branch-extension approach below instead.
- Dialog checkbox label is **"Tank port (T)"** — not "Relief to tank" (the port is user-wired to whatever they connect, the label shouldn't assert the mechanism).
- Sprites already exist — do not recreate or modify them: `resources/nodes/pressure_reducing_valve/pressure_reducing_valve.png` (body, untouched) and `resources/nodes/pressure_reducing_valve/pressure_reducing_valve_relief.png` (relief overlay, 200×162px, T port line reaches the bottom edge at x=132..137, center 134.5).
- `ReliefValve` (`simulation/nodes/relief_valve.py`, `graphics/items/base/nodes/relief_valve.py`) is the direct precedent for the conditional-property mechanics (`piloted` → `_update_pilot_anchor()` → `_pilot_overlay` → `paint()` override → dialog checkbox) — deviations must have a reason.

---

### Task 1: Simulation node — `relieving` property, `T` port, extended equations

**Files:**
- Modify: `simulation/nodes/pressure_reducing_valve.py` (full rewrite below)
- Modify: `tests/test_pressure_reducing_valve_hydraulic.py` (additions below — every existing test in this file stays unmodified)

**Interfaces:**
- Consumes: nothing new beyond Task 1 of the base plan (`Node`, `HydraulicMixin`).
- Produces: `PressureReducingValve.relieving: bool` (instance attribute, set from `properties.get("relieving", False)`, only inside the `domain == "hydraulic"` block — same as `p_set`/`flow_var_p`/`flow_var_a`). `PressureReducingValve.flow_var_t` (`f"Q_{id}_T"`) exists as an instance attribute **only when** `self.relieving` is `True` (mirrors `ReliefValve.flow_var_y` under `piloted`). `hydraulic_ports()` returns `{"P": ..., "A": ..., "T": ...}` when relieving, `{"P": ..., "A": ...}` otherwise (unchanged shape). `equations()` returns a 3-element list `[eq_conservation, eq_supply, eq_relief]` when relieving, a 2-element list `[eq_conservation, eq_supply]` otherwise (Task 2's graphics item does not consume this directly, but the full test suite and any future circuit-level code do).

- [ ] **Step 1: Write the failing tests (additions to the existing file)**

Append to `tests/test_pressure_reducing_valve_hydraulic.py` (every test already in the file stays as-is — these are new additions after the existing `test_set_scale_applies_minimum_floors`):

```python
# ---------------------------------------------------------------------------
# relieving=True: T port, 3-port conservation, relief regime
# ---------------------------------------------------------------------------

def make_relieving_valve(p_set=1.5e7):
    valve = PressureReducingValve(
        "prv", domain="hydraulic", properties={"p_set": p_set, "relieving": True},
    )
    valve.add_anchor("P", domain="hydraulic")
    valve.add_anchor("A", domain="hydraulic")
    valve.add_anchor("T", domain="hydraulic")
    valve.anchors["P"].pressure_var = "P_P"
    valve.anchors["A"].pressure_var = "P_A"
    valve.anchors["T"].pressure_var = "P_T"
    return valve


def make_relieving_idx(valve):
    return {
        valve.flow_var_p: 0, valve.flow_var_a: 1, valve.flow_var_t: 2,
        "P_P": 3, "P_A": 4, "P_T": 5,
    }


def test_relieving_false_by_default_no_t_port():
    valve = make_valve()
    assert valve.relieving is False
    assert not hasattr(valve, "flow_var_t")
    assert set(valve.hydraulic_ports().keys()) == {"P", "A"}


def test_relieving_true_adds_t_port():
    valve = make_relieving_valve()
    assert valve.relieving is True
    assert set(valve.hydraulic_ports().keys()) == {"P", "A", "T"}


def test_variables_include_t_flow_and_pressure_when_relieving():
    valve = make_relieving_valve(p_set=2e7)
    assert set(valve.variables) == {
        valve.flow_var_p, valve.flow_var_a, valve.flow_var_t, "P_P", "P_A", "P_T",
    }


def test_bounds_include_t_when_relieving():
    valve = make_relieving_valve()
    assert valve.bounds == {
        valve.flow_var_p: (0.0, None),
        valve.flow_var_a: (None, 0.0),
        valve.flow_var_t: (None, 0.0),
    }


def test_relieving_conservation_is_3_port():
    valve = make_relieving_valve(p_set=1.5e7)
    idx = make_relieving_idx(valve)
    # Q_P + Q_A + Q_T = 2e-4 - 1e-4 - 1e-4 = 0
    x = np.array([2e-4, -1e-4, -1e-4, 1.0e7, 1.0e7, 0.0])
    eq_conservation, _, _ = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9


def test_relief_regime_residual_matches_formula():
    """Inside the closed/relief branch (P_a > p_set, Q_p <= 0), eq_relief
    should equal exactly (P_a - p_set)/P_scale. Not asserted at zero: the
    branch's own root (P_a == p_set) sits exactly on its guard's boundary
    (P_a > p_set), which no floating trial value can land on exactly --
    a converging solver approaches it from above without ever crossing it.
    Check the formula directly instead of asserting an exact root here."""
    valve = make_relieving_valve(p_set=1.5e7)
    idx = make_relieving_idx(valve)
    x = np.array([-2e-5, 1e-4, -8e-5, 1.0e7, 1.6e7, 0.0])  # Q_p<=0, P_a=1.6e7 > p_set
    eq_conservation, eq_supply, eq_relief = valve.equations(x, idx)
    assert abs(eq_conservation) < 1e-9  # -2e-5 + 1e-4 - 8e-5 = 0
    assert abs(eq_supply - (-2e-5) / valve.q_ref) < 1e-12
    assert abs(eq_relief - (1.6e7 - 1.5e7) / valve.p_ref) < 1e-12


def test_relief_regime_residual_shrinks_to_near_zero_as_p_a_approaches_p_set():
    valve = make_relieving_valve(p_set=1.5e7)
    idx = make_relieving_idx(valve)
    x = np.array([0.0, 1e-4, -1e-4, 1.0e7, 1.5e7 + 1e-3, 0.0])  # P_a just barely above p_set
    _, _, eq_relief = valve.equations(x, idx)
    assert abs(eq_relief) < 1e-9


def test_relief_port_is_dead_when_not_in_closed_branch():
    """Outside the closed/relief branch (here: regulating, P_a == p_set,
    P_p above it), Q_T is a dead port -- pinned to zero, same 'dead port'
    pattern ReliefValve/CheckValve already use for their piloted Y port."""
    valve = make_relieving_valve(p_set=1.5e7)
    idx = make_relieving_idx(valve)
    x = np.array([1e-4, -1e-4, 3.0, 2.0e7, 1.5e7, 0.0])  # regulating regime, Q_t trial = 3.0
    _, _, eq_relief = valve.equations(x, idx)
    assert abs(eq_relief - 3.0 / valve.q_ref) < 1e-9  # not zero -- Q_t=3 isn't a root here


def test_initial_guess_seeds_t_flow_when_relieving():
    valve = make_relieving_valve(p_set=1.5e7)
    valve.anchors["P"].pressure = 3e7
    guess = valve.initial_guess
    assert guess[valve.flow_var_t] == 0.0
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `pytest tests/test_pressure_reducing_valve_hydraulic.py -v`
Expected: the pre-existing tests still PASS (unmodified code so far); the new `relieving`-related tests FAIL (`AttributeError: 'PressureReducingValve' object has no attribute 'relieving'` or similar, since the implementation hasn't changed yet).

- [ ] **Step 3: Rewrite the implementation**

Replace the full contents of `simulation/nodes/pressure_reducing_valve.py`:

```python
"""Single-stage, direct-acting pressure reducing valve simulation node.

Normally open -- throttles its own P->A passage to hold the OUTLET
pressure at p_set, and never boosts pressure. No tank port by default:
unlike ReliefValve (simulation/nodes/relief_valve.py), which shunts
excess flow to a T port when the INLET pressure exceeds its threshold,
this valve is in series and simply restricts its own orifice. Modeled
with the same Fischer-Burmeister smoothed complementarity ReliefValve
and CheckValve already use, mirrored to sense P_A (outlet) instead of
P_in.

A third, closed regime is handled outside that FB pairing: if the
outlet is already above p_set (e.g. from external backpressure, or a
stale post-topology-change seed) while forward flow is at or below its
zero lower bound, the FB pairing has no root, so equations() instead
pins Q_P to zero directly.

Optional property `relieving` (default False, mirrors ReliefValve's
`piloted`) adds a real flow port `T`: instead of merely refusing more
inflow while the outlet floats above p_set, the valve actively pulls
P_A back down to p_set via T -- the user wires T to a Reservoir node,
same as any other tank port in this codebase. This is NOT modeled as a
second, independent Fischer-Burmeister pair against (P_A - p_set): that
pairing is satisfied by the same condition (P_A == p_set) as the
supply-side pair, with nothing to decide which port does the work,
making the system rank-deficient exactly at the most commonly visited
state. Instead, the same closed-regime branch above is extended: once
inside it, Q_P stays pinned to zero (as before) and a second equation
directly pins P_A to p_set via T's flow. Outside that branch, T is a
dead port (pinned to zero flow) -- no relief is needed.
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
            self.relieving = bool(self.properties.get("relieving", False))
            if self.relieving:
                self.flow_var_t = f"Q_{self.id}_T"

    @property
    def p_hint(self) -> float:
        return self.p_set

    @property
    def variables(self) -> list:
        if self.domain != "hydraulic":
            return []
        vars_ = [self.flow_var_p, self.flow_var_a]
        if self.relieving:
            vars_.append(self.flow_var_t)
        for anchor_name in self.hydraulic_ports().keys():
            anchor = self.anchors.get(anchor_name)
            if anchor and anchor.pressure_var:
                vars_.append(anchor.pressure_var)
        return vars_

    @property
    def bounds(self):
        b = {
            self.flow_var_p: (0.0, None),   # Q_P never negative -- forward flow only
            self.flow_var_a: (None, 0.0),   # Q_A never positive
        }
        if self.relieving:
            b[self.flow_var_t] = (None, 0.0)   # Q_T never positive -- only leaves via T
        return b

    def hydraulic_ports(self) -> dict:
        if self.domain != "hydraulic":
            return {}
        ports = {"P": self.flow_var_p, "A": self.flow_var_a}
        if self.relieving:
            ports["T"] = self.flow_var_t
        return ports

    def equations(self, x, idx):
        Q_p = x[idx[self.flow_var_p]]
        Q_a = x[idx[self.flow_var_a]]
        P_p = x[idx[self.anchors["P"].pressure_var]]
        P_a = x[idx[self.anchors["A"].pressure_var]]

        Q_scale = self.q_ref
        P_scale = self.p_ref

        if self.relieving:
            Q_t = x[idx[self.flow_var_t]]
            eq_conservation = (Q_p + Q_a + Q_t) / Q_scale
        else:
            eq_conservation = (Q_p + Q_a) / Q_scale

        if P_a > self.p_set and Q_p <= 0:
            # Closed: outlet already above setpoint from something this
            # valve cannot supply (external backpressure, or a stale
            # solver seed right after a topology change) and there is no
            # forward flow trying to happen. The 2-regime FB below has no
            # root here (a = p_set - P_a stays negative regardless of b),
            # which would otherwise fault the whole circuit for a state a
            # real valve handles by simply staying shut. Pin Q_p to
            # exactly zero instead of forcing the (infeasible) FB pairing.
            eq_supply = Q_p / Q_scale
            if self.relieving:
                # Actively pull the outlet back down via T instead of
                # leaving it floating above p_set.
                eq_relief = (P_a - self.p_set) / P_scale
        else:
            # a >= 0: P_A never exceeds p_set. b >= 0: the valve only drops
            # pressure (P_P >= P_A), never boosts it. Exactly one is zero:
            # either fully open (b=0, P_A=P_P) or regulating (a=0, P_A=p_set).
            a = (self.p_set - P_a) / P_scale
            b = (P_p - P_a) / P_scale
            eq_supply = a + b - math.sqrt(a * a + b * b)
            if self.relieving:
                eq_relief = Q_t / Q_scale  # dead port here -- no relief needed

        if self.relieving:
            return [eq_conservation, eq_supply, eq_relief]
        return [eq_conservation, eq_supply]

    @property
    def initial_guess(self) -> dict:
        if self.domain != "hydraulic":
            return {}
        anchor_p = self.anchors.get("P")
        p_hint = getattr(anchor_p, "pressure", 0.0) if anchor_p else 0.0
        if isinstance(p_hint, str):
            p_hint = 0.0
        guess = {
            self.flow_var_p: 0.0,
            self.flow_var_a: 0.0,
            self.anchors["P"].pressure_var: p_hint,
        }
        if self.relieving:
            guess[self.flow_var_t] = 0.0
        return guess

    def update(self, outputs=None):
        pass  # no external state -- everything lives inside the solver

    def set_scale(self, p_ref: float, q_ref: float) -> None:
        self.p_ref = max(p_ref, 1e5)    # minimum 1 bar -- realistic scale
        self.q_ref = max(q_ref, 1e-10)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pressure_reducing_valve_hydraulic.py -v`
Expected: PASS — all tests green, including every pre-existing test (unmodified) and every new one.

- [ ] **Step 5: Commit**

```bash
git add simulation/nodes/pressure_reducing_valve.py tests/test_pressure_reducing_valve_hydraulic.py
git commit -m "feat: add relieving property and T port to pressure reducing valve"
```

---

### Task 2: Graphics item — `relieving` overlay, `T` anchor, dialog checkbox

**Files:**
- Modify: `graphics/items/base/nodes/pressure_reducing_valve.py` (full rewrite below)
- Modify: `tests/test_pressure_reducing_valve_item.py` (additions below — every existing test in this file stays unmodified)

**Interfaces:**
- Consumes: Task 1's `PressureReducingValve.relieving`, `hydraulic_ports()` including `"T"` when relieving.
- Produces: `PressureReducingValve._relief_overlay` (instance attribute, `None` when `relieving=False`, a `QPixmap` when `True` — mirrors `ReliefValve._pilot_overlay`), `_update_relief_anchor()` (instance method, adds/removes anchor `"T"` and sets `_relief_overlay` based on `self.properties.get("relieving")`), dialog field `dialog._field_relieving` (a bool/checkbox field from `PropertiesDialog.add_bool_field`).

- [ ] **Step 1: Write the failing tests (additions to the existing file)**

Append to `tests/test_pressure_reducing_valve_item.py` (every test already in the file stays as-is):

```python
def test_relieving_false_by_default_no_t_anchor_or_overlay():
    node = PressureReducingValve(domain="hydraulic")
    assert "T" not in node.anchors
    assert node._relief_overlay is None


def test_relieving_true_adds_t_anchor_and_overlay():
    node = PressureReducingValve(domain="hydraulic")
    node.properties["relieving"] = True
    node.apply_properties()

    assert "T" in node.anchors
    assert (node.anchors["T"].pos().x(), node.anchors["T"].pos().y()) == (
        node.width * 134.5 / 200, node.height,
    )
    assert node._relief_overlay is not None


def test_toggling_relieving_back_to_false_removes_t_anchor():
    node = PressureReducingValve(domain="hydraulic")
    node.properties["relieving"] = True
    node.apply_properties()
    assert "T" in node.anchors

    node.properties["relieving"] = False
    node.apply_properties()
    assert "T" not in node.anchors
    assert node._relief_overlay is None


def test_build_properties_dialog_reflects_relieving_property():
    node = PressureReducingValve(domain="hydraulic")
    node.properties["p_set"] = 1.5e7
    node.properties["relieving"] = True

    dialog = node.build_properties_dialog()

    assert dialog._field_p_set.text() == "15000000.0"
    assert dialog._field_relieving.isChecked() is True


def test_apply_properties_from_dialog_updates_relieving_and_anchors():
    node = PressureReducingValve(domain="hydraulic")
    dialog = node.build_properties_dialog()
    dialog._field_p_set.setText("2e7")
    dialog._field_relieving.setChecked(True)

    node.apply_properties_from_dialog(dialog)

    assert node.properties["p_set"] == 2e7
    assert node.properties["relieving"] is True
    assert "T" in node.anchors
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `pytest tests/test_pressure_reducing_valve_item.py -v`
Expected: pre-existing tests still PASS; new `relieving`-related tests FAIL (`AttributeError`/`KeyError`, implementation unchanged so far).

- [ ] **Step 3: Rewrite the implementation**

Replace the full contents of `graphics/items/base/nodes/pressure_reducing_valve.py`:

```python
"""Graphics node for the single-stage, direct-acting pressure reducing valve.

Sprite layout
-------------
Width x Height: 200 x 162 px
Anchor P (top)  : (width*98.5/200, 0)          inlet  -> top
Anchor A (base) : (width*98.5/200, height)     outlet -> bottom
Anchor T (base) : (width*134.5/200, height)    relief -> bottom
                  present only when properties["relieving"] is True.
                  Measured from pressure_reducing_valve_relief.png's
                  opaque pixels: the line reaches the bottom edge at
                  x=132..137, center 134.5.

Sprites
-------
pressure_reducing_valve.png        -- body (ISO schematic, single stage).
pressure_reducing_valve_relief.png -- tank/relief port overlay (T port
                                       line), drawn on top of the body
                                       when relieving=True.
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
        self.properties = {"relieving": False}
        self.pixmap = QPixmap(f"{_SPRITE_DIR}/pressure_reducing_valve.png")
        self.width  = self.pixmap.width()
        self.height = self.pixmap.height()

        self.add_anchor(AnchorItem("P", QPointF(self.width*98.5/200, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))
        self.add_anchor(AnchorItem("A", QPointF(self.width*98.5/200, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))

        self._pixmap_relief = QPixmap(f"{_SPRITE_DIR}/pressure_reducing_valve_relief.png")
        self._relief_overlay = None
        self._update_relief_anchor()

    def _update_relief_anchor(self) -> None:
        """Adds/removes the T anchor and the relief overlay based on
        self.properties. Called in setup() and whenever the property
        changes (apply_properties / apply_properties_from_dialog)."""
        if self.properties.get("relieving"):
            self.add_anchor(AnchorItem(
                "T", QPointF(self.width*134.5/200, self.height), node=self, domain=self.domain,
                exit_directions={"external": ["bottom"]},
            ))
            self._relief_overlay = self._pixmap_relief
        else:
            self.remove_anchor("T")
            self._relief_overlay = None

    def apply_properties(self) -> None:
        self._update_relief_anchor()
        self.update()

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self._relief_overlay is not None:
            painter.save()
            painter.translate(self._visual_offset)
            self.draw_pixmap(painter, QPointF(0, 0), self._relief_overlay)
            painter.restore()

    def build_properties_dialog(self):
        dialog = PropertiesDialog(title=self.tr("Pressure Reducing Valve — Properties"))
        dialog._field_p_set = dialog.add_number_field(
            self.tr("Setpoint pressure (Pa)"), placeholder="ex: 1.5e7  (= 150 bar)",
            value=self.properties.get("p_set"),
            required=True,
        )
        dialog._field_relieving = dialog.add_bool_field(
            self.tr("Tank port (T)"), value=self.properties.get("relieving", False),
        )
        return dialog

    def apply_properties_from_dialog(self, dialog):
        p_set_text = dialog._field_p_set.text().strip()
        self.properties["p_set"] = float(p_set_text) if p_set_text else None
        self.properties["relieving"] = dialog._field_relieving.isChecked()
        self._update_relief_anchor()
        self.update()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pressure_reducing_valve_item.py -v`
Expected: PASS — all tests green.

- [ ] **Step 5: Commit**

```bash
git add graphics/items/base/nodes/pressure_reducing_valve.py tests/test_pressure_reducing_valve_item.py
git commit -m "feat: add relieving overlay, T anchor and dialog checkbox to pressure reducing valve graphics item"
```

---

### Task 3: i18n catalog entries for the new checkbox label

**Files:**
- Modify: `resources/i18n/circuiteditor_en.ts`
- Modify: `resources/i18n/circuiteditor_pt_BR.ts`
- Modify (regenerated, committed binaries): `resources/i18n/circuiteditor_en.qm`, `resources/i18n/circuiteditor_pt_BR.qm`

**Interfaces:** none (no Python code produced/consumed) — this task exists because the base pressure-reducing-valve feature's final review specifically flagged missing catalog entries as an Important finding, and this plan adds exactly one new translatable string (`"Tank port (T)"`, `graphics/items/base/nodes/pressure_reducing_valve.py` inside `build_properties_dialog`). Catching it in-plan avoids repeating that review finding.

- [ ] **Step 1: Find the new string's line number**

Run: `grep -n 'Tank port' graphics/items/base/nodes/pressure_reducing_valve.py`
Expected: one match, e.g. `graphics/items/base/nodes/pressure_reducing_valve.py:62:        dialog._field_relieving = dialog.add_bool_field(`. Note the line number of the `self.tr("Tank port (T)")` call itself (the following line) for the `<location line="N">` entry.

- [ ] **Step 2: Add the message entry to `circuiteditor_en.ts`**

Find the existing `<name>PressureReducingValve</name>` context block (added by the base feature) and add one more `<message>` entry inside it, after the existing three, following the exact same format:

```xml
    <message>
        <location filename="..\..\graphics\items\base\nodes\pressure_reducing_valve.py" line="N" />
        <source>Tank port (T)</source>
        <translation type="unfinished" />
    </message>
```

(Replace `N` with the line number found in Step 1.)

- [ ] **Step 3: Add the message entry to `circuiteditor_pt_BR.ts`**

Same context block, same location line, with a real translation:

```xml
    <message>
        <location filename="..\..\graphics\items\base\nodes\pressure_reducing_valve.py" line="N" />
        <source>Tank port (T)</source>
        <translation>Via de tanque (T)</translation>
    </message>
```

- [ ] **Step 4: Recompile the catalogs**

Run: `python scripts/compile_translations.py`
Expected: reports both `.qm` files compiled. `circuiteditor_pt_BR.qm` will show as modified in `git status` (real translation payload changed); `circuiteditor_en.qm` may be byte-identical and not show as modified — this is expected `lrelease` behavior (unfinished translations carry no payload in the compiled binary), not an error, already seen once before on this same component.

- [ ] **Step 5: Run the translation-catalog test**

Run: `pytest tests/test_pt_br_translation_loads.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add resources/i18n/circuiteditor_en.ts resources/i18n/circuiteditor_pt_BR.ts resources/i18n/circuiteditor_en.qm resources/i18n/circuiteditor_pt_BR.qm
git commit -m "feat: add i18n catalog entry for pressure reducing valve tank port checkbox"
```

---

### Task 4: Full test suite regression check

**Files:** none created/modified — verification only.

**Interfaces:** none.

- [ ] **Step 1: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS — no regressions anywhere (palette discovery, node registry, translation catalog, existing pressure-reducing-valve tests, etc.).

- [ ] **Step 2: If green, no further action needed. If red, fix before considering the plan done.**

No commit for this task — it's a checkpoint, not a change.
