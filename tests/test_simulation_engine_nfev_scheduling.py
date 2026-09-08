"""SimulationEngine wires NfevScheduler into the hydraulic domain's
retry loop: each zc-escalation attempt gets a max_nfev budget that
starts cheap and only grows when the previous attempt's residual was
close to converging (see simulation/hydraulic/scale_context.py's
NfevScheduler docstring, and simulation_engine.py's _update_hydraulic_domain).

Root cause this replaces: a flat max_nfev=6000 on every retry, which
profiling showed burning the full budget on almost every attempt of a
real circuit's cold start without improving the residual (16.8s for a
single step). This test suite checks the WIRING (the scheduler is
actually consulted and its state resets on convergence) -- the actual
speed and correctness improvement was verified by hand against a real
circuit (docs/superpowers or session notes), not re-derived here since
timing assertions in a test suite are inherently flaky.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.simulation_engine import SimulationEngine
from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
from simulation.nodes.reservoir import Reservoir
from simulation.nodes.check_valve.throttle_check_valve import ThrottleCheckValve
from simulation.connections import Connection
import simulation.hydraulic.solver as solver_mod


def _pump_throttle_reservoir_circuit():
    """Same minimal end-to-end circuit as
    test_fixed_displacement_pump.py's throttle test -- pump discharging
    through a restricted throttle into a reservoir, forcing at least one
    real least_squares/fsolve solve."""
    pump = FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": 1e-4})
    pump.add_anchor("P", domain="hydraulic")
    pump.add_anchor("S", domain="hydraulic")

    valve = ThrottleCheckValve("tcv", domain="hydraulic", properties={"k": 1e-7})
    valve.add_anchor("X", domain="hydraulic")
    valve.add_anchor("Y", domain="hydraulic")

    res_suction = Reservoir("res_suction", domain="hydraulic", properties={"pressure": 0.0})
    res_suction.add_anchor("T", domain="hydraulic")
    res_out = Reservoir("res_out", domain="hydraulic", properties={"pressure": 0.0})
    res_out.add_anchor("T", domain="hydraulic")

    conn1 = Connection(pump.get_anchor("S"), res_suction.get_anchor("T"))
    conn2 = Connection(pump.get_anchor("P"), valve.get_anchor("X"))
    conn3 = Connection(valve.get_anchor("Y"), res_out.get_anchor("T"))

    nodes = {"pump": pump, "tcv": valve, "res_suction": res_suction, "res_out": res_out}
    connections = {c.id: c for c in (conn1, conn2, conn3)}
    return nodes, connections


def test_engine_starts_new_circuits_at_the_scheduler_cheapest_rung(monkeypatch):
    used_budgets = []
    orig_solve = solver_mod.NonlinearSystemSolver.solve

    def spy_solve(self, x0_dict, ctx):
        used_budgets.append(ctx.max_nfev)
        return orig_solve(self, x0_dict, ctx)

    monkeypatch.setattr(solver_mod.NonlinearSystemSolver, "solve", spy_solve)

    nodes, connections = _pump_throttle_reservoir_circuit()
    engine = SimulationEngine(nodes, connections)
    engine.run_until_stable()

    assert used_budgets, "the solver was never actually invoked"
    assert used_budgets[0] == engine._nfev_scheduler.ladder[0]


def test_nfev_rung_and_residual_reset_after_convergence():
    nodes, connections = _pump_throttle_reservoir_circuit()
    engine = SimulationEngine(nodes, connections)
    engine.run_until_stable()

    assert engine._nfev_rung == 0
    assert engine._last_residual_norm is None
