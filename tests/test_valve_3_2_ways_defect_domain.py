"""Confere que Valve_3_2_Ways captura _k_default (igual Valve_4_2_Ways) --
sem isso, defect_active/_clear_defect (definidos em DirectionalValve, a
classe base compartilhada) silenciosamente não restauram k nem detectam
desvio, exatamente a armadilha apontada na revisão final da feature original
(ver docs/superpowers/plans/2026-08-04-hydraulic-defect-simulation.md)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.nodes.directional_valve.valve_3_2_ways import Valve_3_2_Ways


def _make_valve(k=1e-7, body_state=0):
    valve = Valve_3_2_Ways("v32", domain="hydraulic", properties={"k": k})
    valve.body_state = body_state
    for port in ("P", "A", "R"):
        valve.add_anchor(port, domain="hydraulic")
        valve.anchors[port].pressure_var = f"P_{port}"
    return valve


def test_fresh_instance_has_no_defect():
    valve = _make_valve()
    assert valve.defect_active is False
    assert valve._stuck_defect is False


def test_set_defect_changes_k_and_marks_active():
    valve = _make_valve(k=1e-7)
    valve.handle_command({"action": "set_defect", "k": 5e-8, "stuck": False})
    assert valve.k == 5e-8
    assert valve.defect_active is True


def test_clear_defect_restores_original_k():
    valve = _make_valve(k=1e-7)
    valve.handle_command({"action": "set_defect", "k": 5e-8, "stuck": True})
    valve.handle_command({"action": "clear_defect"})
    assert valve.k == 1e-7
    assert valve._stuck_defect is False
    assert valve.defect_active is False


def test_stuck_defect_freezes_body_state():
    valve = _make_valve(body_state=0)
    valve.handle_command({"action": "set_defect", "k": valve.k, "stuck": True})
    valve.handle_command({"type": "actuator", "side": "left", "value": 1})
    valve.update()
    assert valve.body_state == 0  # continua travada


def test_set_defect_changes_orifice_residual_and_clear_defect_restores_it():
    """Prova o efeito no solver, não só o atributo -- mesmo espírito do
    teste equivalente para a 4/2 vias."""
    k = 1e-7
    valve = _make_valve(k=k, body_state=0)
    assert valve.get_internal_connections() == [("A", "R")]

    idx = {"Q_v32_in": 0, "Q_v32_out": 1, "P_A": 2, "P_R": 3}
    import numpy as np
    x = np.zeros(4)
    x[idx["Q_v32_in"]] = 1e-4
    x[idx["Q_v32_out"]] = -1e-4
    import math
    x[idx["P_A"]] = math.copysign((1e-4 / k) ** 2, 1e-4)
    x[idx["P_R"]] = 0.0

    eqs_before = valve.equations(x, idx)

    valve.handle_command({"action": "set_defect", "k": 5e-8, "stuck": False})
    eqs_after = valve.equations(x, idx)
    assert eqs_after != eqs_before

    valve.handle_command({"action": "clear_defect"})
    eqs_restored = valve.equations(x, idx)
    assert eqs_restored == eqs_before
