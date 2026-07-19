import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.nodes.fixed_displacement_pump import FixedDisplacementPump


def make_pump(Q=1e-4):
    pump = FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": Q})
    return pump


def test_bounds_force_q_in_positive_and_q_out_negative():
    """Convenção do domínio (node_protocol.py): Q>0 = entrando no
    componente. Fluido entra na bomba por P (sucção) e sai por S
    (descarga) -- Q_in deve ser positivo, Q_out negativo."""
    pump = make_pump(Q=2e-4)
    bounds = pump.bounds
    lo_in, hi_in = bounds[pump.flow_in_var]
    lo_out, hi_out = bounds[pump.flow_out_var]

    assert lo_in > 0 and hi_in > 0
    assert lo_out < 0 and hi_out < 0


def test_initial_guess_matches_bounds_sign():
    """initial_guess sempre foi sobrescrito pelo clip nos bounds
    (np.clip em NonlinearSystemSolver.solve) -- essa asserção prova que
    os dois não se contradizem mais (antes da correção, discordavam nos
    dois sinais, tornando o initial_guess sempre descartado)."""
    pump = make_pump()
    guess = pump.initial_guess
    lo_in, hi_in = pump.bounds[pump.flow_in_var]
    lo_out, hi_out = pump.bounds[pump.flow_out_var]

    assert lo_in <= guess[pump.flow_in_var] <= hi_in
    assert lo_out <= guess[pump.flow_out_var] <= hi_out


def test_equations_root_matches_bounds():
    import numpy as np
    pump = make_pump(Q=2e-4)
    idx = {pump.flow_in_var: 0, pump.flow_out_var: 1}
    x = np.array([2e-4, -2e-4])
    eq_conservation, eq_fixed = pump.equations(x, idx)
    assert abs(eq_conservation) < 1e-12
    assert abs(eq_fixed) < 1e-12


# ---------------------------------------------------------------------------
# Ponta a ponta: bomba -> estrangulador (sentido restrito) -> reservatório
# ---------------------------------------------------------------------------

def test_pump_forcing_reverse_direction_through_throttle_valve_end_to_end():
    """Regressão do bug relatado: bomba empurrando fluido pra dentro do
    lado X de um estrangulador (sentido restrito) deve resultar em Q_X
    POSITIVO (entrando, per convenção) e pressão se acumulando -- antes
    da correção, a convenção invertida da bomba fazia Q_X sair negativo
    e a válvula (corretamente implementada) interpretava isso como
    sentido livre, sem queda de pressão nenhuma."""
    from simulation.simulation_engine import SimulationEngine
    from simulation.nodes.reservoir import Reservoir
    from simulation.connections import Connection
    from simulation.nodes.check_valve.throttle_check_valve import ThrottleCheckValve

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

    conn1 = Connection(pump.get_anchor("P"), res_suction.get_anchor("T"))
    conn2 = Connection(pump.get_anchor("S"), valve.get_anchor("X"))
    conn3 = Connection(valve.get_anchor("Y"), res_out.get_anchor("T"))

    nodes = {"pump": pump, "tcv": valve, "res_suction": res_suction, "res_out": res_out}
    connections = {c.id: c for c in (conn1, conn2, conn3)}

    engine = SimulationEngine(nodes, connections)
    engine.run_until_stable()

    x_flow = valve.get_anchor("X").flow
    x_pressure = valve.get_anchor("X").pressure

    assert x_flow > 0  # entrando em X -- sentido restrito, como esperado
    assert x_pressure > 1000.0  # pressão se acumula pra vencer o orifício
    assert valve.get_visual_state() == "closed"  # sentido restrito
