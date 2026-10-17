# Pilot-Operated Relief Valve Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hydraulic pilot-operated relief valve with a vent / remote-control port X as a new, self-contained palette component.

**Architecture:** A new domain node (`simulation/nodes/pilot_operated_relief_valve.py`) with its own 5 equations (orifice P→chamber, pilot-stage FB, main-stage FB, two flow balances); port X is a real flow port, so an unconnected X is plugged through the engine's existing per-anchor continuity. A new graphics item (`graphics/items/base/nodes/pilot_operated_relief_valve.py`) with measured anchors, an automatic plug overlay on X, properties/defect dialogs; discovered by the node registry via `palette_meta()`. No core file changes.

**Tech Stack:** Python 3.14, PyQt6, NumPy/SciPy (existing solver), pytest, Qt Linguist `.ts`/`.qm` catalogs.

**Spec:** `docs/superpowers/specs/2026-10-17-pilot-operated-relief-valve-design.md`

## Global Constraints

- Do NOT modify `simulation/simulation_engine.py`, anything under `simulation/hydraulic/`, `main_window/ui/registry/node_registry.py`, `simulation/nodes/relief_valve.py`, `graphics/items/base/nodes/relief_valve.py`, or any other existing core file. If a change there looks unavoidable, STOP and report why.
- Allowed changes: the two new component modules, new test files, `tests/simulate_json.py`, `resources/i18n/circuiteditor_{en,pt_BR}.{ts,qm}`, the already-drawn sprites/xcf, the spec and this plan.
- `node_type = "pilot_operated_relief_valve"`; domain class `PilotOperatedReliefValve` in `simulation/nodes/`; graphics class `PilotOperatedReliefValve` in `graphics/items/base/nodes/`.
- `p_set` = pilot spring setting (required, `> 0`); `p_vent` = main-poppet spring (optional, default `3e5`, `> 0`); orifice `K_ORIFICE = 3e-8` class constant (not a property).
- With X free the valve regulates at `p_set + p_vent`; steady state `P_P = min(p_set, P_remote) + p_vent`.
- `DEFECT_FIELDS = {"p_set": "p_set"}` only.
- Code, comments, commit messages in English, terse (no narrative comments).
- Run Python from `tcc-circuitos/` with the project venv: `../venv/Scripts/python.exe -m pytest ...`.
- Never run `pylupdate6 --no-obsolete`; this plan adds catalog entries by hand (no pylupdate6 run at all).

## Review Focus

1. Pump flow smaller than the pilot flow (`Q < K·√p_vent`, pilot-only regime) → still regulates between `p_set` and `p_set + p_vent`, no solver failure. Pinned in Task 2 (`test_small_pump_flow_pilot_only_regime`).
2. `p_vent` field left empty in the dialog → property removed, domain default `3e5` used. Pinned in Task 3 (`test_apply_dialog_empty_p_vent_removes_property`).
3. JSON saved without `p_vent` loads and simulates with the default. Pinned in Task 3 (`test_json_round_trip_without_p_vent`) + Task 1 (`test_p_vent_defaults_when_missing`).
4. Deleting the X connection brings the plug back. Pinned in Task 3 (`test_plug_overlay_follows_x_connection`).
5. T backpressured above `p_set` (pilot stage passive) → exact root with `P_X = P_T`, `P_P = P_T + p_vent`, no NaN. Pinned in Task 1 (`test_passive_regime_when_t_backpressured`).

---

### Task 0: Branch and commit design assets

**Files:**
- Commit: `docs/superpowers/specs/2026-10-17-pilot-operated-relief-valve-design.md`, `docs/superpowers/plans/2026-10-17-pilot-operated-relief-valve.md`, `resources/nodes/pilot_operated_relief_valve/*.png`, `resources/gimp_files/pilot_operated_relief_valve*.xcf`

**Interfaces:**
- Consumes: nothing.
- Produces: branch `pilot-operated-relief-valve`.

- [ ] **Step 1: Check the working tree**

Run: `git status --short`
If anything other than the files listed above is modified/untracked (e.g. unrelated cylinder work, `resources/i18n/*`), STOP and ask the user to commit or stash it first — Task 4 edits the i18n catalogs and must not mix with unrelated changes.

- [ ] **Step 2: Create the branch**

```bash
git checkout -b pilot-operated-relief-valve
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-10-17-pilot-operated-relief-valve-design.md docs/superpowers/plans/2026-10-17-pilot-operated-relief-valve.md resources/nodes/pilot_operated_relief_valve resources/gimp_files/pilot_operated_relief_valve.xcf resources/gimp_files/pilot_operated_relief_valve_x_plug.xcf
git commit -m "docs: pilot-operated relief valve spec, plan and sprites"
```

---

### Task 1: Domain node and equation unit tests

**Files:**
- Create: `simulation/nodes/pilot_operated_relief_valve.py`
- Test: `tests/test_pilot_operated_relief_valve_hydraulic.py`

**Interfaces:**
- Consumes: `Node`, `DefectMixin`, `HydraulicMixin` (as `ReliefValve` does).
- Produces: `PilotOperatedReliefValve(node_id, *, domain, properties)` with attributes `p_set: float`, `p_vent: float`, `K_ORIFICE = 3e-8`, `DEFAULT_P_VENT = 3e5`, flow var names `flow_var_p`, `flow_var_t`, `flow_var_x`, `flow_var_main`, `flow_var_pilot` (`f"Q_{id}_P"`, `_T`, `_X`, `_main`, `_pilot`), `hydraulic_ports() -> {"P","T","X"}`, `p_hint == p_set + p_vent`.

- [ ] **Step 1: Write the failing tests**

`tests/test_pilot_operated_relief_valve_hydraulic.py`:

```python
import sys
import math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pytest

from simulation.nodes.pilot_operated_relief_valve import PilotOperatedReliefValve

P_SET = 1.0e7
P_VENT = 3.0e5
K = PilotOperatedReliefValve.K_ORIFICE


def make_valve(p_set=P_SET, p_vent=P_VENT):
    props = {"p_set": p_set}
    if p_vent is not None:
        props["p_vent"] = p_vent
    v = PilotOperatedReliefValve("po", domain="hydraulic", properties=props)
    for name in ("P", "T", "X"):
        v.add_anchor(name, domain="hydraulic")
        v.anchors[name].pressure_var = f"P_{name}"
    v.set_scale(P_SET, 1e-3)
    return v


def residuals(v, **values):
    idx = {name: i for i, name in enumerate(v.variables)}
    x = np.zeros(len(idx))
    for name, value in values.items():
        x[idx[name]] = value
    return v.equations(x, idx)


def state(v, *, q_p=0.0, q_t=0.0, q_x=0.0, q_main=0.0, q_pilot=0.0, p_p=0.0, p_t=0.0, p_x=0.0):
    return {
        v.flow_var_p: q_p, v.flow_var_t: q_t, v.flow_var_x: q_x,
        v.flow_var_main: q_main, v.flow_var_pilot: q_pilot,
        "P_P": p_p, "P_T": p_t, "P_X": p_x,
    }


def assert_root(eqs):
    assert len(eqs) == 5
    for e in eqs:
        assert abs(e) < 1e-9


# --- construction -----------------------------------------------------------

def test_node_type():
    assert make_valve().type == "pilot_operated_relief_valve"


def test_missing_p_set_raises():
    with pytest.raises(ValueError, match="p_set"):
        PilotOperatedReliefValve("po", domain="hydraulic", properties={})


@pytest.mark.parametrize("props", [{"p_set": 0.0}, {"p_set": -1.0}, {"p_set": 1e7, "p_vent": 0.0}, {"p_set": 1e7, "p_vent": -5.0}])
def test_non_positive_settings_raise(props):
    with pytest.raises(ValueError):
        PilotOperatedReliefValve("po", domain="hydraulic", properties=props)


def test_p_vent_defaults_when_missing():
    v = make_valve(p_vent=None)
    assert v.p_vent == PilotOperatedReliefValve.DEFAULT_P_VENT == 3e5


def test_p_hint_is_system_pressure():
    assert make_valve().p_hint == P_SET + P_VENT


# --- ports / variables / bounds --------------------------------------------

def test_x_is_a_flow_port_not_a_dead_port():
    v = make_valve()
    assert set(v.hydraulic_ports()) == {"P", "T", "X"}
    assert v.hydraulic_ports()["X"] == v.flow_var_x
    assert not hasattr(v, "dead_ports") or v.dead_ports() == []


def test_variables():
    v = make_valve()
    assert set(v.variables) == {
        v.flow_var_p, v.flow_var_t, v.flow_var_x, v.flow_var_main, v.flow_var_pilot,
        "P_P", "P_T", "P_X",
    }


def test_bounds():
    v = make_valve()
    assert v.bounds == {
        v.flow_var_p: (0.0, None),
        v.flow_var_t: (None, 0.0),
        v.flow_var_main: (0.0, None),
        v.flow_var_pilot: (0.0, None),
    }


# --- exact roots per regime ------------------------------------------------

def test_closed_regime_is_root():
    v = make_valve()
    assert_root(residuals(v, **state(v, p_p=5e6, p_x=5e6)))


def test_regulating_regime_is_root():
    v = make_valve()
    q = 1e-3
    q_orif = K * math.sqrt(P_VENT)
    assert_root(residuals(v, **state(
        v, q_p=q, q_t=-q, q_main=q - q_orif, q_pilot=q_orif,
        p_p=P_SET + P_VENT, p_x=P_SET,
    )))


def test_vented_regime_is_root():
    v = make_valve()
    q = 1e-3
    q_orif = K * math.sqrt(P_VENT)
    assert_root(residuals(v, **state(
        v, q_p=q, q_t=-(q - q_orif), q_x=-q_orif, q_main=q - q_orif,
        p_p=P_VENT, p_x=0.0,
    )))


def test_pilot_only_regime_is_root():
    v = make_valve()
    q = 0.5 * K * math.sqrt(P_VENT)
    assert_root(residuals(v, **state(
        v, q_p=q, q_t=-q, q_pilot=q,
        p_p=P_SET + (q / K) ** 2, p_x=P_SET,
    )))


def test_regulating_pressure_off_target_is_not_root():
    v = make_valve()
    q = 1e-3
    q_orif = K * math.sqrt(P_VENT)
    eqs = residuals(v, **state(
        v, q_p=q, q_t=-q, q_main=q - q_orif, q_pilot=q_orif,
        p_p=P_SET, p_x=P_SET - P_VENT,
    ))
    assert max(abs(e) for e in eqs) > 1e-6


def test_passive_regime_when_t_backpressured():
    # T above p_set: pilot stage is passive (P_X = P_T), main stage
    # regulates on top of it -> P_P = P_T + p_vent.
    v = make_valve()
    p_back = 2.0e7
    q = 1e-3
    q_orif = K * math.sqrt(P_VENT)
    eqs = residuals(v, **state(
        v, q_p=q, q_t=-q, q_main=q - q_orif, q_pilot=q_orif,
        p_p=p_back + P_VENT, p_x=p_back, p_t=p_back,
    ))
    assert all(math.isfinite(e) for e in eqs)
    assert_root(eqs)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../venv/Scripts/python.exe -m pytest tests/test_pilot_operated_relief_valve_hydraulic.py -v`
Expected: FAIL / collection error — `ModuleNotFoundError: No module named 'simulation.nodes.pilot_operated_relief_valve'`

- [ ] **Step 3: Implement the node**

`simulation/nodes/pilot_operated_relief_valve.py`:

```python
"""Pilot-operated (two-stage) relief valve with vent / remote-control
port X.

Model (quasi-static), see
docs/superpowers/specs/2026-10-17-pilot-operated-relief-valve-design.md:
  - orifice P -> chamber (turbulent, ThrottleValve form, K_ORIFICE)
  - pilot stage chamber -> T: FB, threshold p_set on P_X
  - main stage P -> T: FB, threshold P_X + p_vent on P_P
Chamber pressure is port X's pressure. X is a real flow port: unconnected,
the engine's per-anchor continuity forces Q_X = 0 (plugged), so no
dead_ports() and no internal pressure variable.

Steady state: P_P = min(p_set, P_remote) + p_vent.
"""

import math
from simulation.nodes.nodes import Node
from simulation.nodes.defect import DefectMixin
from simulation.hydraulic import HydraulicMixin


def _relief_fb(p_in, p_out, threshold, q, P_scale, Q_scale):
    # Same residual as ReliefValve.equations(), passive-regime guard included.
    if p_out > threshold and p_out >= p_in and q > 0:
        return (p_in - p_out) / P_scale
    a = (threshold - p_in) / P_scale
    b = q / Q_scale
    return a + b - math.sqrt(a * a + b * b)


class PilotOperatedReliefValve(DefectMixin, Node, HydraulicMixin):
    # misadjusted pilot spring
    DEFECT_FIELDS = {"p_set": "p_set"}

    K_ORIFICE = 3e-8        # m3/s/sqrt(Pa): ~1 L/min pilot flow at 3 bar
    DEFAULT_P_VENT = 3e5    # Pa, main-poppet spring

    def __init__(self, node_id: str, *, domain=None, properties=None, **kwargs):
        super().__init__(node_id, "pilot_operated_relief_valve", domain=domain, properties=properties)
        if self.domain == "hydraulic":
            p_set = self.properties.get("p_set")
            if p_set is None:
                raise ValueError(f"PilotOperatedReliefValve '{self.id}': required property 'p_set' is not set.")
            self.p_set = float(p_set)
            if self.p_set <= 0:
                raise ValueError(f"PilotOperatedReliefValve '{self.id}': 'p_set' must be positive.")
            self.p_vent = float(self.properties.get("p_vent", self.DEFAULT_P_VENT))
            if self.p_vent <= 0:
                raise ValueError(f"PilotOperatedReliefValve '{self.id}': 'p_vent' must be positive.")
            self.flow_var_p = f"Q_{self.id}_P"
            self.flow_var_t = f"Q_{self.id}_T"
            self.flow_var_x = f"Q_{self.id}_X"
            self.flow_var_main = f"Q_{self.id}_main"
            self.flow_var_pilot = f"Q_{self.id}_pilot"

    @property
    def p_hint(self) -> float:
        return self.p_set + self.p_vent

    @property
    def variables(self) -> list:
        if self.domain != "hydraulic":
            return []
        vars_ = [self.flow_var_p, self.flow_var_t, self.flow_var_x,
                 self.flow_var_main, self.flow_var_pilot]
        for anchor_name in self.hydraulic_ports().keys():
            anchor = self.anchors.get(anchor_name)
            if anchor and anchor.pressure_var:
                vars_.append(anchor.pressure_var)
        return vars_

    @property
    def bounds(self):
        return {
            self.flow_var_p: (0.0, None),
            self.flow_var_t: (None, 0.0),
            self.flow_var_main: (0.0, None),
            self.flow_var_pilot: (0.0, None),
        }

    def hydraulic_ports(self) -> dict:
        if self.domain != "hydraulic":
            return {}
        return {"P": self.flow_var_p, "T": self.flow_var_t, "X": self.flow_var_x}

    def equations(self, x, idx):
        Q_p = x[idx[self.flow_var_p]]
        Q_t = x[idx[self.flow_var_t]]
        Q_x = x[idx[self.flow_var_x]]
        Q_main = x[idx[self.flow_var_main]]
        Q_pilot = x[idx[self.flow_var_pilot]]
        P_p = x[idx[self.anchors["P"].pressure_var]]
        P_t = x[idx[self.anchors["T"].pressure_var]]
        P_x = x[idx[self.anchors["X"].pressure_var]]

        Q_scale = self.q_ref
        P_scale = self.p_ref

        Q_orif = Q_p - Q_main

        eq_t = (Q_t + Q_main + Q_pilot) / Q_scale
        eq_chamber = (Q_orif - Q_pilot + Q_x) / Q_scale
        eq_orifice = ((P_p - P_x) - math.copysign((Q_orif / self.K_ORIFICE) ** 2, Q_orif)) / P_scale
        eq_pilot = _relief_fb(P_x, P_t, self.p_set, Q_pilot, P_scale, Q_scale)
        eq_main = _relief_fb(P_p, P_t, P_x + self.p_vent, Q_main, P_scale, Q_scale)

        return [eq_t, eq_chamber, eq_orifice, eq_pilot, eq_main]

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
            self.flow_var_t: 0.0,
            self.flow_var_x: 0.0,
            self.flow_var_main: 0.0,
            self.flow_var_pilot: 0.0,
            self.anchors["P"].pressure_var: p_hint,
        }

    def update(self, outputs=None):
        pass  # no state of its own

    def set_scale(self, p_ref: float, q_ref: float) -> None:
        self.p_ref = max(p_ref, 1e5)
        self.q_ref = max(q_ref, 1e-10)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../venv/Scripts/python.exe -m pytest tests/test_pilot_operated_relief_valve_hydraulic.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add simulation/nodes/pilot_operated_relief_valve.py tests/test_pilot_operated_relief_valve_hydraulic.py
git commit -m "feat: pilot-operated relief valve domain node"
```

---

### Task 2: End-to-end regulation and defect tests

These exercise the Task 1 node through the real `SimulationEngine`. They are expected to pass without code changes (the equation system was validated by a spike); if one fails, debug the node (superpowers:systematic-debugging) — do not change the engine.

**Files:**
- Test: `tests/test_pilot_operated_relief_valve_end_to_end.py`
- Test: `tests/test_pilot_operated_relief_valve_defect.py` (domain part only; item part added in Task 3)

**Interfaces:**
- Consumes: `PilotOperatedReliefValve` (Task 1); `SimulationEngine(nodes, connections).run_until_stable(dt=1.0)`; `Connection(a, b)`; `Reservoir`, `FixedDisplacementPump`, `ReliefValve`, `ThrottleValve`, `Valve_2_2_Ways` (body_state 1 = P↔A open, 0 = blocked); `node.handle_command({"action": "set_defect"|"clear_defect", ...})`.
- Produces: nothing new.

- [ ] **Step 1: Write the end-to-end tests**

`tests/test_pilot_operated_relief_valve_end_to_end.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from simulation.connections import Connection
from simulation.nodes.directional_valve.valve_2_2_ways import Valve_2_2_Ways
from simulation.nodes.pilot_operated_relief_valve import PilotOperatedReliefValve
from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
from simulation.nodes.relief_valve import ReliefValve
from simulation.nodes.reservoir import Reservoir
from simulation.nodes.throttle_valve import ThrottleValve
from simulation.simulation_engine import SimulationEngine

P_SET = 1.0e7
P_VENT = 3.0e5
Q = 1e-3


def _node(cls, nid, anchors, **props):
    n = cls(nid, domain="hydraulic", properties=props)
    for a in anchors:
        n.add_anchor(a, domain="hydraulic")
    return n


class Circuit:
    """Fixed-displacement pump -> valve under test -> tank."""

    def __init__(self, q=Q):
        self.nodes = {}
        self.conns = []
        self.pump = self.add(FixedDisplacementPump, "pump", "PS", Q=q)
        self.connect(self.pump, "S", self.add(Reservoir, "res_s", "T", pressure=0.0), "T")
        self.tank = self.add(Reservoir, "tank", "T", pressure=0.0)

    def add(self, cls, nid, anchors, **props):
        n = _node(cls, nid, anchors, **props)
        self.nodes[nid] = n
        return n

    def connect(self, a, an, b, bn):
        self.conns.append(Connection(a.get_anchor(an), b.get_anchor(bn)))

    def run(self):
        engine = SimulationEngine(self.nodes, {c.id: c for c in self.conns})
        engine.run_until_stable(dt=1.0)
        return engine

    def p_pump(self):
        return self.pump.get_anchor("P").pressure


def with_valve(q=Q, p_set=P_SET, p_vent=P_VENT):
    c = Circuit(q)
    v = c.add(PilotOperatedReliefValve, "po", "PTX", p_set=p_set, p_vent=p_vent)
    c.connect(c.pump, "P", v, "P")
    c.connect(v, "T", c.tank, "T")
    return c, v


def add_remote_relief(c, v, p_r):
    rem = c.add(ReliefValve, "remote", "PT", p_set=p_r)
    c.connect(v, "X", rem, "P")
    c.connect(rem, "T", c.add(Reservoir, "tank_r", "T", pressure=0.0), "T")


# 1. X free

def test_x_free_regulates_at_p_set_plus_p_vent():
    c, v = with_valve()
    c.run()
    assert c.p_pump() == pytest.approx(P_SET + P_VENT, rel=1e-3)
    assert v.get_anchor("X").flow == pytest.approx(0.0, abs=1e-9)
    assert v.get_anchor("T").flow == pytest.approx(-Q, rel=1e-3)


def test_x_free_matches_direct_relief_and_discrete_build():
    c, _ = with_valve()
    c.run()
    p_component = c.p_pump()

    d = Circuit()
    rv = d.add(ReliefValve, "rv", "PT", p_set=P_SET + P_VENT)
    d.connect(d.pump, "P", rv, "P")
    d.connect(rv, "T", d.tank, "T")
    d.run()

    m = Circuit()
    orif = m.add(ThrottleValve, "orif", "XY", k=PilotOperatedReliefValve.K_ORIFICE)
    main = m.add(ReliefValve, "main", "PTY", p_set=P_VENT, piloted=True)
    pilot = m.add(ReliefValve, "pilot", "PT", p_set=P_SET)
    m.connect(m.pump, "P", main, "P")
    m.connect(m.pump, "P", orif, "X")
    m.connect(orif, "Y", main, "Y")
    m.connect(orif, "Y", pilot, "P")
    m.connect(main, "T", m.tank, "T")
    m.connect(pilot, "T", m.tank, "T")
    m.run()

    assert p_component == pytest.approx(d.p_pump(), rel=1e-3)
    assert p_component == pytest.approx(m.p_pump(), rel=1e-3)


# 2. X to tank

def test_x_to_tank_regulates_at_p_vent():
    c, v = with_valve()
    c.connect(v, "X", c.add(Reservoir, "tank_x", "T", pressure=0.0), "T")
    c.run()
    assert c.p_pump() == pytest.approx(P_VENT, rel=1e-3)
    assert v.get_anchor("X").flow < 0  # pilot flow leaves through X


# 3. / 4. remote relief

def test_remote_relief_below_p_set_regulates_at_p_r_plus_p_vent():
    c, v = with_valve()
    add_remote_relief(c, v, 5.0e6)
    c.run()
    assert c.p_pump() == pytest.approx(5.0e6 + P_VENT, rel=1e-3)


def test_remote_relief_above_p_set_internal_pilot_wins():
    c, v = with_valve()
    add_remote_relief(c, v, 1.5e7)
    c.run()
    assert c.p_pump() == pytest.approx(P_SET + P_VENT, rel=1e-3)


# 5. vent through a 2/2 switched mid-simulation

def test_vent_valve_switched_mid_simulation():
    c, v = with_valve()
    vent = c.add(Valve_2_2_Ways, "vent", "PA", k=1e-5)
    vent.body_state = 0  # blocked
    c.connect(v, "X", vent, "P")
    c.connect(vent, "A", c.add(Reservoir, "tank_x", "T", pressure=0.0), "T")
    engine = SimulationEngine(c.nodes, {cn.id: cn for cn in c.conns})

    engine.run_until_stable(dt=1.0)
    assert c.p_pump() == pytest.approx(P_SET + P_VENT, rel=1e-3)

    vent.body_state = 1
    engine.run_until_stable(dt=1.0)
    assert c.p_pump() == pytest.approx(P_VENT, rel=1e-2)

    vent.body_state = 0
    engine.run_until_stable(dt=1.0)
    assert c.p_pump() == pytest.approx(P_SET + P_VENT, rel=1e-3)


# Review focus 1: pilot-only regime

def test_small_pump_flow_pilot_only_regime():
    q = 0.5 * PilotOperatedReliefValve.K_ORIFICE * P_VENT ** 0.5
    c, _ = with_valve(q=q)
    c.run()
    expected = P_SET + (q / PilotOperatedReliefValve.K_ORIFICE) ** 2
    assert c.p_pump() == pytest.approx(expected, rel=1e-3)
    assert P_SET < c.p_pump() < P_SET + P_VENT
```

- [ ] **Step 2: Write the domain defect tests**

`tests/test_pilot_operated_relief_valve_defect.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from simulation.connections import Connection
from simulation.nodes.pilot_operated_relief_valve import PilotOperatedReliefValve
from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
from simulation.nodes.reservoir import Reservoir
from simulation.simulation_engine import SimulationEngine

P_SET = 1.0e7
P_VENT = 3.0e5


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------

def _valve(p_set=P_SET):
    v = PilotOperatedReliefValve("po", domain="hydraulic", properties={"p_set": p_set, "p_vent": P_VENT})
    for a in "PTX":
        v.add_anchor(a, domain="hydraulic")
    return v


def test_fresh_valve_has_no_defect():
    assert _valve().defect_active is False


def test_set_defect_changes_p_set_and_hint():
    v = _valve()
    v.handle_command({"action": "set_defect", "p_set": 5e6})
    assert v.p_set == 5e6
    assert v.p_hint == 5e6 + P_VENT
    assert v.defect_active is True


def test_clear_defect_restores_p_set():
    v = _valve()
    v.handle_command({"action": "set_defect", "p_set": 5e6})
    v.handle_command({"action": "clear_defect"})
    assert v.p_set == P_SET
    assert v.defect_active is False


def _circuit(q=1e-3):
    v = _valve()
    pump = FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": q})
    pump.add_anchor("P", domain="hydraulic")
    pump.add_anchor("S", domain="hydraulic")
    res_s = Reservoir("res_s", domain="hydraulic", properties={"pressure": 0.0})
    res_s.add_anchor("T", domain="hydraulic")
    res_t = Reservoir("res_t", domain="hydraulic", properties={"pressure": 0.0})
    res_t.add_anchor("T", domain="hydraulic")
    conns = [
        Connection(pump.get_anchor("P"), v.get_anchor("P")),
        Connection(pump.get_anchor("S"), res_s.get_anchor("T")),
        Connection(v.get_anchor("T"), res_t.get_anchor("T")),
    ]
    nodes = {"po": v, "pump": pump, "res_s": res_s, "res_t": res_t}
    return SimulationEngine(nodes, {c.id: c for c in conns}), v


@pytest.mark.parametrize("factor", [0.5, 1.5])
def test_defect_applied_and_cleared_mid_run(factor):
    engine, v = _circuit()
    engine.run_until_stable(dt=1.0)
    assert v.get_anchor("P").pressure == pytest.approx(P_SET + P_VENT, rel=1e-3)

    v.handle_command({"action": "set_defect", "p_set": P_SET * factor})
    engine.run_until_stable(dt=1.0)
    assert v.get_anchor("P").pressure == pytest.approx(P_SET * factor + P_VENT, rel=1e-3)

    v.handle_command({"action": "clear_defect"})
    engine.run_until_stable(dt=1.0)
    assert v.get_anchor("P").pressure == pytest.approx(P_SET + P_VENT, rel=1e-3)
```

- [ ] **Step 3: Run both files**

Run: `../venv/Scripts/python.exe -m pytest tests/test_pilot_operated_relief_valve_end_to_end.py tests/test_pilot_operated_relief_valve_defect.py -v`
Expected: all PASS. On failure: print `P_X`, `Q_main`, `Q_pilot` for the failing case and debug the node's equations against the spec; the spike in the spec reproduced cases 1–4 exactly with the discrete build.

- [ ] **Step 4: Commit**

```bash
git add tests/test_pilot_operated_relief_valve_end_to_end.py tests/test_pilot_operated_relief_valve_defect.py
git commit -m "test: end-to-end venting, remote control and defect for pilot-operated relief"
```

---

### Task 3: Graphics item (anchors, plug overlay, dialogs, persistence)

**Files:**
- Create: `graphics/items/base/nodes/pilot_operated_relief_valve.py`
- Test: `tests/test_pilot_operated_relief_valve_item.py`
- Modify: `tests/test_pilot_operated_relief_valve_defect.py` (append item section)

**Interfaces:**
- Consumes: `PilotOperatedReliefValve` domain node (Task 1); `NodeItem`, `PaletteMeta`, `PropertiesDialog.add_number_field(label, placeholder="", value=None, required=False, min_value=None)`, `DefectFieldSpec(key, label, kind, placeholder=, min_value=)`, `AnchorItem(name, pos, node=, domain=, exit_directions=)`, `AnchorItem.connection_count()`, `AnchorItem.refresh_junction_dot()`, `NodeItem.to_dict()` / `NodeItem.from_dict(data)`, `GraphBuilder`.
- Produces: graphics class `PilotOperatedReliefValve` with `node_type = "pilot_operated_relief_valve"`, `simulation_cls`, `x_plugged() -> bool`, dialog attributes `_field_p_set`, `_field_p_vent`.

- [ ] **Step 1: Write the failing item tests**

`tests/test_pilot_operated_relief_valve_item.py`:

```python
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.pilot_operated_relief_valve import PilotOperatedReliefValve
from simulation.graph_builder import GraphBuilder
from simulation.nodes.pilot_operated_relief_valve import PilotOperatedReliefValve as Node


def make_item(**props):
    item = PilotOperatedReliefValve(domain="hydraulic")
    item.properties.update(props)
    return item


def test_node_type_and_simulation_cls():
    assert PilotOperatedReliefValve.node_type == "pilot_operated_relief_valve"
    assert PilotOperatedReliefValve.simulation_cls is Node


def test_palette_meta():
    meta = PilotOperatedReliefValve.palette_meta()
    assert meta.domains == ("hydraulic",)
    assert meta.name == "Relief Valve (pilot-operated)"
    assert meta.sprite.endswith("pilot_operated_relief_valve.png")


def test_sprite_size():
    item = make_item()
    assert (item.width, item.height) == (254, 161)


def test_anchor_positions_and_exits():
    item = make_item()
    w, h = item.width, item.height
    assert set(item.anchors) == {"P", "T", "X"}
    pos = {n: (a.pos().x(), a.pos().y()) for n, a in item.anchors.items()}
    assert pos["P"] == (w * 98.5 / 254, 0)
    assert pos["T"] == (w * 98.5 / 254, h)
    assert pos["X"] == (w, h * 19.5 / 161)
    assert item.anchors["P"].exit_directions == {"external": ["top"]}
    assert item.anchors["T"].exit_directions == {"external": ["bottom"]}
    assert item.anchors["X"].exit_directions == {"external": ["right"]}


def test_plug_overlay_follows_x_connection():
    item = make_item()
    x = item.anchors["X"]
    repaints = []
    item.update = lambda *a, **k: repaints.append(1)

    assert item.x_plugged() is True

    conn = SimpleNamespace(source_anchor=x, target_anchor=None)
    item.connections.append(conn)
    x.refresh_junction_dot()
    assert item.x_plugged() is False
    assert repaints

    item.connections.remove(conn)
    repaints.clear()
    x.refresh_junction_dot()
    assert item.x_plugged() is True
    assert repaints


def test_connection_on_other_port_keeps_plug():
    item = make_item()
    item.connections.append(SimpleNamespace(source_anchor=item.anchors["P"], target_anchor=None))
    assert item.x_plugged() is True


def test_dialog_prefilled():
    item = make_item(p_set=1e7, p_vent=4e5)
    dialog = item.build_properties_dialog()
    assert float(dialog._field_p_set.text()) == 1e7
    assert float(dialog._field_p_vent.text()) == 4e5


def test_apply_dialog_sets_both_properties():
    item = make_item()
    dialog = item.build_properties_dialog()
    dialog._field_p_set.setText("1.2e7")
    dialog._field_p_vent.setText("5e5")
    item.apply_properties_from_dialog(dialog)
    assert item.properties["p_set"] == 1.2e7
    assert item.properties["p_vent"] == 5e5


def test_apply_dialog_empty_p_vent_removes_property():
    item = make_item(p_set=1e7, p_vent=5e5)
    dialog = item.build_properties_dialog()
    dialog._field_p_vent.setText("")
    item.apply_properties_from_dialog(dialog)
    assert "p_vent" not in item.properties
    node = Node("po", domain="hydraulic", properties=item.properties)
    assert node.p_vent == Node.DEFAULT_P_VENT


def test_json_round_trip_with_p_vent():
    item = make_item(p_set=1e7, p_vent=4e5)
    loaded = NodeItem.from_dict(item.to_dict())
    assert isinstance(loaded, PilotOperatedReliefValve)
    assert loaded.properties == {"p_set": 1e7, "p_vent": 4e5}
    assert set(loaded.anchors) == {"P", "T", "X"}


def test_json_round_trip_without_p_vent():
    item = make_item(p_set=1e7)
    loaded = NodeItem.from_dict(item.to_dict())
    assert "p_vent" not in loaded.properties
    assert Node("po", domain="hydraulic", properties=loaded.properties).p_vent == 3e5


def test_graph_builder_accepts_unconnected_x():
    item = make_item(p_set=1e7)
    builder = GraphBuilder()
    node = builder.add_node_from_item(item)
    builder.raise_if_errors()  # unconnected X must not be a validation error
    assert set(node.anchors) == {"P", "T", "X"}
```

Append to `tests/test_pilot_operated_relief_valve_defect.py`:

```python


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.pilot_operated_relief_valve import PilotOperatedReliefValve as Item


def test_item_defect_fields_one_spec_in_hydraulic():
    specs = Item(domain="hydraulic").defect_fields()
    assert [s.key for s in specs] == ["p_set"]
    assert specs[0].kind == "number"
    assert specs[0].min_value == 0
    assert specs[0].label == "Pilot setting p_set (Pa)"


def test_item_apply_defect_emits_set_defect_float():
    item = Item(domain="hydraulic")
    item.properties["p_set"] = P_SET
    dialog = item.build_defect_dialog()
    dialog.defect_widget("p_set").setText("5e6")
    received = []
    item.command.connect(lambda nid, payload: received.append(payload))
    item.apply_defect_from_dialog(dialog)
    assert received == [{"action": "set_defect", "p_set": 5e6}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../venv/Scripts/python.exe -m pytest tests/test_pilot_operated_relief_valve_item.py tests/test_pilot_operated_relief_valve_defect.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'graphics.items.base.nodes.pilot_operated_relief_valve'`

- [ ] **Step 3: Implement the item**

`graphics/items/base/nodes/pilot_operated_relief_valve.py`:

```python
"""Graphics node for the pilot-operated relief valve (vent port X).

Sprite layout
-------------
Width x Height: 254 x 161 px
Anchor P (top)   : (width*98.5/254, 0)        exit -> top
Anchor T (base)  : (width*98.5/254, height)   exit -> bottom
Anchor X (vent)  : (width, height*19.5/161)   exit -> right
Measured on the PNGs: P/T opaque pixels on the top/bottom rows at
x=97..100; the X line's last dash touches the right edge at y=17..22.

Sprites
-------
pilot_operated_relief_valve.png        -- body, X line open
pilot_operated_relief_valve_x_plug.png -- plug bar only, drawn while X
                                          has no connection (unconnected
                                          X is plugged in the solver too)
"""

from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, QCoreApplication
from simulation.nodes.pilot_operated_relief_valve import (
    PilotOperatedReliefValve as PilotOperatedReliefValveNode,
)

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.node_descriptor import PaletteMeta
from graphics.utils.properties_dialog import PropertiesDialog
from graphics.utils.defect_dialog import DefectFieldSpec
from ....anchors.anchor import AnchorItem

_SPRITE_DIR = "resources/nodes/pilot_operated_relief_valve"


class _VentAnchor(AnchorItem):
    """Repaints the node when X gains/loses a connection (plug overlay)."""

    def refresh_junction_dot(self) -> None:
        super().refresh_junction_dot()
        if self.node is not None:
            self.node.update()


class PilotOperatedReliefValve(NodeItem):
    node_type = "pilot_operated_relief_valve"
    simulation_cls = PilotOperatedReliefValveNode

    @classmethod
    def palette_meta(cls):
        return PaletteMeta(
            domains=("hydraulic",),
            sprite=f"{_SPRITE_DIR}/pilot_operated_relief_valve.png",
            name=QCoreApplication.translate("PilotOperatedReliefValve", "Relief Valve (pilot-operated)"),
        )

    def setup(self) -> None:
        self.properties = {}
        self.pixmap = QPixmap(f"{_SPRITE_DIR}/pilot_operated_relief_valve.png")
        self._pixmap_plug = QPixmap(f"{_SPRITE_DIR}/pilot_operated_relief_valve_x_plug.png")
        self.width = self.pixmap.width()
        self.height = self.pixmap.height()

        x_pt = self.width * 98.5 / 254
        self.add_anchor(AnchorItem("T", QPointF(x_pt, self.height), node=self, domain=self.domain, exit_directions={"external": ["bottom"]}))
        self.add_anchor(AnchorItem("P", QPointF(x_pt, 0), node=self, domain=self.domain, exit_directions={"external": ["top"]}))
        self.add_anchor(_VentAnchor("X", QPointF(self.width, self.height * 19.5 / 161), node=self, domain=self.domain, exit_directions={"external": ["right"]}))

    def x_plugged(self) -> bool:
        anchor = self.anchors.get("X")
        return anchor is not None and anchor.connection_count() == 0

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.x_plugged():
            painter.save()
            painter.translate(self._visual_offset)
            self.draw_pixmap(painter, QPointF(0, 0), self._pixmap_plug)
            painter.restore()

    def build_properties_dialog(self):
        dialog = PropertiesDialog(title=self.tr("Pilot-Operated Relief Valve — Properties"))
        dialog._field_p_set = dialog.add_number_field(
            self.tr("Pilot setting p_set (Pa)"), placeholder="ex: 1e7  (= 100 bar)",
            value=self.properties.get("p_set"),
            required=True,
        )
        dialog._field_p_vent = dialog.add_number_field(
            self.tr("Main-stage spring p_vent (Pa)"), placeholder="3e5  (= 3 bar, default)",
            value=self.properties.get("p_vent"),
        )
        return dialog

    def apply_properties_from_dialog(self, dialog):
        p_set_text = dialog._field_p_set.text().strip()
        self.properties["p_set"] = float(p_set_text) if p_set_text else None
        p_vent_text = dialog._field_p_vent.text().strip()
        if p_vent_text:
            self.properties["p_vent"] = float(p_vent_text)
        else:
            self.properties.pop("p_vent", None)
        self.update()

    def defect_fields(self):
        if self.domain != "hydraulic":
            return []
        return [DefectFieldSpec(
            "p_set", self.tr("Pilot setting p_set (Pa)"), "number",
            placeholder="ex: 1e7  (= 100 bar)", min_value=0,
        )]
```

Notes for the implementer:
- `palette_meta()` declares hydraulic only, so the item is never created in another domain from the palette; the domain node guards `domain != "hydraulic"` like `ReliefValve`.
- If `NodeItem.__init__` builds the item before `setup()` sets `self.properties` (check `node_item.py:119-180`), keep `self.properties = {}` in `setup()` exactly like `ReliefValve.setup()` does with its own defaults.

- [ ] **Step 4: Run tests to verify they pass**

Run: `../venv/Scripts/python.exe -m pytest tests/test_pilot_operated_relief_valve_item.py tests/test_pilot_operated_relief_valve_defect.py -v`
Expected: all PASS.

- [ ] **Step 5: Check palette discovery**

Run: `../venv/Scripts/python.exe -c "import sys; from PyQt6.QtWidgets import QApplication; app = QApplication(sys.argv); from main_window.ui.registry.node_registry import _discover_palette_nodes; print([c.__name__ for c in _discover_palette_nodes() if 'Pilot' in c.__name__])"`
Expected: `['PilotOperatedReliefValve']`

- [ ] **Step 6: Commit**

```bash
git add graphics/items/base/nodes/pilot_operated_relief_valve.py tests/test_pilot_operated_relief_valve_item.py tests/test_pilot_operated_relief_valve_defect.py
git commit -m "feat: pilot-operated relief valve graphics item with automatic X plug overlay"
```

---

### Task 4: pt_BR translations

**Files:**
- Modify: `resources/i18n/circuiteditor_pt_BR.ts`, `resources/i18n/circuiteditor_en.ts`
- Regenerate: `resources/i18n/circuiteditor_pt_BR.qm`, `resources/i18n/circuiteditor_en.qm`
- Test: `tests/test_pilot_operated_relief_valve_item.py` (append)

**Interfaces:**
- Consumes: the 4 source strings from Task 3, context `PilotOperatedReliefValve`: `Relief Valve (pilot-operated)`, `Pilot-Operated Relief Valve — Properties`, `Pilot setting p_set (Pa)`, `Main-stage spring p_vent (Pa)`.
- Produces: compiled catalogs.

Catalog entries are added by hand (no pylupdate6 run): a full regen marks ~40 in-use strings `vanished` (known pylupdate6 blind spots) and would need manual recovery.

- [ ] **Step 1: Write the failing translation test**

Append to `tests/test_pilot_operated_relief_valve_item.py`:

```python


from main_window.language import language_manager
from tests.defect_test_helpers import form_label_texts


def test_pt_br_translations():
    language_manager.apply_language(app, "pt_BR")
    try:
        assert PilotOperatedReliefValve.palette_meta().name == "Válvula de Alívio (pré-operada)"
        dialog = make_item(p_set=1e7).build_properties_dialog()
        try:
            assert dialog.windowTitle() == "Válvula de Alívio Pré-operada — Propriedades"
            labels = form_label_texts(dialog)
            assert "Ajuste do piloto p_set (Pa)" in labels
            assert "Mola do estágio principal p_vent (Pa)" in labels
        finally:
            dialog.close()
    finally:
        language_manager.apply_language(app, "en")
```

- [ ] **Step 2: Run to verify it fails**

Run: `../venv/Scripts/python.exe -m pytest tests/test_pilot_operated_relief_valve_item.py::test_pt_br_translations -v`
Expected: FAIL — palette name still `Relief Valve (pilot-operated)`.

- [ ] **Step 3: Add the catalog entries**

Get the source line numbers: `grep -n "translate\|self.tr(" graphics/items/base/nodes/pilot_operated_relief_valve.py`

In `resources/i18n/circuiteditor_pt_BR.ts`, insert a new context between `</context>` of `OrValve` and `<context>` of `PressureGauge` (alphabetical order), replacing `L1..L4` with the real line numbers (the `p_set` label appears twice — use the dialog's line):

```xml
<context>
    <name>PilotOperatedReliefValve</name>
    <message>
        <location filename="..\..\graphics\items\base\nodes\pilot_operated_relief_valve.py" line="L1" />
        <source>Relief Valve (pilot-operated)</source>
        <translation>Válvula de Alívio (pré-operada)</translation>
    </message>
    <message>
        <location filename="..\..\graphics\items\base\nodes\pilot_operated_relief_valve.py" line="L2" />
        <source>Pilot-Operated Relief Valve — Properties</source>
        <translation>Válvula de Alívio Pré-operada — Propriedades</translation>
    </message>
    <message>
        <location filename="..\..\graphics\items\base\nodes\pilot_operated_relief_valve.py" line="L3" />
        <source>Pilot setting p_set (Pa)</source>
        <translation>Ajuste do piloto p_set (Pa)</translation>
    </message>
    <message>
        <location filename="..\..\graphics\items\base\nodes\pilot_operated_relief_valve.py" line="L4" />
        <source>Main-stage spring p_vent (Pa)</source>
        <translation>Mola do estágio principal p_vent (Pa)</translation>
    </message>
</context>
```

Match the surrounding file's exact formatting (the existing file closes one context and opens the next on the same line: `</context><context>`). In `resources/i18n/circuiteditor_en.ts`, insert the same block at the same alphabetical position with every `<translation>` replaced by `<translation type="unfinished" />`.

- [ ] **Step 4: Compile the catalogs**

Run: `PATH="../venv/Scripts:$PATH" ../venv/Scripts/python.exe scripts/compile_translations.py`
Expected: both `.qm` files rewritten, no errors.

- [ ] **Step 5: Run to verify it passes**

Run: `../venv/Scripts/python.exe -m pytest tests/test_pilot_operated_relief_valve_item.py tests/test_pilot_operated_relief_valve_defect.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add resources/i18n/circuiteditor_pt_BR.ts resources/i18n/circuiteditor_en.ts resources/i18n/circuiteditor_pt_BR.qm resources/i18n/circuiteditor_en.qm tests/test_pilot_operated_relief_valve_item.py
git commit -m "feat: pt_BR translations for pilot-operated relief valve"
```

---

### Task 5: simulate_json support, full suite, scope check

**Files:**
- Modify: `tests/simulate_json.py` (`_get_node_classes`, `ANCHORS_BY_TYPE`)
- Test: `tests/test_pilot_operated_relief_valve_hydraulic.py` (append)

**Interfaces:**
- Consumes: `tests.simulate_json.ANCHORS_BY_TYPE`, `_get_node_classes()`; JSON `"type"` is the graphics class name (`NodeItem.to_dict()` writes `self.__class__.__name__`), i.e. `"PilotOperatedReliefValve"`.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pilot_operated_relief_valve_hydraulic.py`:

```python


def test_registered_in_simulate_json():
    from tests.simulate_json import ANCHORS_BY_TYPE, _get_node_classes
    assert _get_node_classes()["PilotOperatedReliefValve"] is PilotOperatedReliefValve
    assert ANCHORS_BY_TYPE["PilotOperatedReliefValve"] == ["P", "T", "X"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `../venv/Scripts/python.exe -m pytest tests/test_pilot_operated_relief_valve_hydraulic.py::test_registered_in_simulate_json -v`
Expected: FAIL — `KeyError: 'PilotOperatedReliefValve'`

- [ ] **Step 3: Register the type**

In `tests/simulate_json.py`, `_get_node_classes()`: add the import next to `ReliefValve`'s

```python
    from simulation.nodes.pilot_operated_relief_valve import PilotOperatedReliefValve
```

and the dict entry after `"ReliefValve": ReliefValve,`

```python
        "PilotOperatedReliefValve":   PilotOperatedReliefValve,
```

In `ANCHORS_BY_TYPE`, after `"ReliefValve": ["P", "T"],`:

```python
    "PilotOperatedReliefValve":  ["P", "T", "X"],
```

- [ ] **Step 4: Run to verify it passes**

Run: `../venv/Scripts/python.exe -m pytest tests/test_pilot_operated_relief_valve_hydraulic.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/simulate_json.py tests/test_pilot_operated_relief_valve_hydraulic.py
git commit -m "test: register pilot-operated relief valve in simulate_json"
```

- [ ] **Step 6: Full suite**

Run: `../venv/Scripts/python.exe -m pytest -q`
Expected: all PASS (no failures, no new errors). Report the totals.

- [ ] **Step 7: Scope check**

Run: `git diff --stat main...HEAD`
Expected: only these paths — `docs/superpowers/specs/2026-10-17-pilot-operated-relief-valve-design.md`, `docs/superpowers/plans/2026-10-17-pilot-operated-relief-valve.md`, `resources/nodes/pilot_operated_relief_valve/*`, `resources/gimp_files/pilot_operated_relief_valve*.xcf`, `simulation/nodes/pilot_operated_relief_valve.py`, `graphics/items/base/nodes/pilot_operated_relief_valve.py`, `tests/test_pilot_operated_relief_valve_*.py`, `tests/simulate_json.py`, `resources/i18n/circuiteditor_{en,pt_BR}.{ts,qm}`. Anything else is a constraint violation — revert it and report.

- [ ] **Step 8: Manual check in the app (user)**

Ask the user to open the app, place the valve, confirm the plug shows on X, disappears when wiring X, comes back when deleting the wire, and that a pump + valve circuit reads `p_set + p_vent` on the gauge.
