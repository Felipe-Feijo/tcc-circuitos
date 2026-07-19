import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.nodes.fixed_displacement_pump import FixedDisplacementPump


def make_pump(Q=1e-4):
    pump = FixedDisplacementPump("pump", domain="hydraulic", properties={"Q": Q})
    return pump


def test_bounds_force_p_negative_and_s_positive():
    """P (topo do sprite) é a descarga/pressão -- fluido SAI da bomba ali,
    logo negativo (convenção node_protocol.py: Q>0 = entrando no
    componente). S (embaixo, ligado ao reservatório) é a sucção -- fluido
    ENTRA ali, logo positivo."""
    pump = make_pump(Q=2e-4)
    bounds = pump.bounds
    lo_p, hi_p = bounds[pump.flow_in_var]   # flow_in_var está ligado à porta P
    lo_s, hi_s = bounds[pump.flow_out_var]  # flow_out_var está ligado à porta S

    assert lo_p < 0 and hi_p < 0
    assert lo_s > 0 and hi_s > 0


def test_equations_root_matches_bounds():
    import numpy as np
    pump = make_pump(Q=2e-4)
    idx = {pump.flow_in_var: 0, pump.flow_out_var: 1}
    x = np.array([-2e-4, 2e-4])
    eq_conservation, eq_fixed = pump.equations(x, idx)
    assert abs(eq_conservation) < 1e-12
    assert abs(eq_fixed) < 1e-12


# ---------------------------------------------------------------------------
# Ponta a ponta: bomba (descarga em P) -> estrangulador -> reservatório
# ---------------------------------------------------------------------------

def test_pump_forcing_reverse_direction_through_throttle_valve_end_to_end():
    """Bomba descarregando (porta P, topo) pra dentro do lado X de um
    estrangulador -- sentido restrito -- deve resultar em Q_X POSITIVO
    (entrando na válvula, per convenção) e pressão se acumulando pra
    vencer o orifício."""
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

    # S (sucção) puxa do reservatório embaixo; P (descarga) empurra pra
    # dentro da válvula.
    conn1 = Connection(pump.get_anchor("S"), res_suction.get_anchor("T"))
    conn2 = Connection(pump.get_anchor("P"), valve.get_anchor("X"))
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
