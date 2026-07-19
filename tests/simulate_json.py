"""
tests/simulate_json.py
======================
Ferramenta de diagnóstico headless para circuitos hidráulicos.

Recebe um JSON de circuito (mesmo formato do editor gráfico), monta o
grafo de simulação sem PyQt e roda N passos, imprimindo um relatório
detalhado de pressões, vazões e estado de cada componente.

Uso:
    python tests/simulate_json.py caminho/para/circuito.json [--steps N] [--dt DT] [--debug]

Exemplo:
    python tests/simulate_json.py teste.json --steps 5 --dt 0.05 --debug
"""

import sys
import json
import argparse
import math
from pathlib import Path

# Garante que o root do projeto está no path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from simulation.nodes.nodes import Node, Anchor
from simulation.connections import Connection
from simulation.simulation_engine import SimulationEngine

# ---------------------------------------------------------------------------
# Mapa de tipos → classes de simulação
# ---------------------------------------------------------------------------

def _get_node_classes():
    from simulation.nodes.reservoir import Reservoir
    from simulation.nodes.relief_valve import DirectOperatedReliefValve
    from simulation.nodes.pumps.fixed_displacement_pump import FixedDisplacementPump
    from simulation.nodes.directional_valve.valve_3_2_ways import Valve_3_2_Ways
    from simulation.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways
    from simulation.nodes.directional_valve.valve_5_2_ways import Valve_5_2_Ways
    from simulation.nodes.cylinder.single_acting_cylinder import SingleActingCylinder
    from simulation.nodes.cylinder.double_acting_cylinder import DoubleActingCylinder

    return {
        "Reservoir":                  Reservoir,
        "DirectOperatedReliefValve":  DirectOperatedReliefValve,
        "FixedDisplacementPump":      FixedDisplacementPump,
        "Valve_3_2_Ways":             Valve_3_2_Ways,
        "Valve_4_2_Ways":             Valve_4_2_Ways,
        "Valve_5_2_Ways":             Valve_5_2_Ways,
        "SingleActingCylinder":       SingleActingCylinder,
        "DoubleActingCylinder":       DoubleActingCylinder,
    }

# ---------------------------------------------------------------------------
# Âncoras por tipo de componente (nome → lista de anchor_names)
# ---------------------------------------------------------------------------

ANCHORS_BY_TYPE = {
    "Reservoir":                 ["T"],
    "DirectOperatedReliefValve": ["P", "T"],
    "FixedDisplacementPump":     ["P", "S"],
    "Valve_3_2_Ways":            ["P", "A", "R"],
    "Valve_4_2_Ways":            ["P", "A", "B", "T"],
    "Valve_5_2_Ways":            ["P", "A", "B", "T1", "T2"],
    "SingleActingCylinder":      ["A"],
    "DoubleActingCylinder":      ["A", "B"],
}

# ---------------------------------------------------------------------------
# Carregador de JSON → nós + conexões de simulação
# ---------------------------------------------------------------------------

def load_circuit(path: str) -> tuple[dict, list]:
    """
    Lê o JSON do circuito e devolve (nodes_dict, connections_list)
    prontos para o SimulationEngine.
    """
    with open(path) as f:
        data = json.load(f)

    node_classes = _get_node_classes()
    nodes: dict[str, Node] = {}
    # mapeia (node_id, anchor_name) → Anchor, para construir conexões
    anchor_index: dict[tuple, Anchor] = {}

    # ---- instancia nós ----
    for n in data["nodes"]:
        nid    = n["id"]
        ntype  = n["type"]
        domain = n.get("domain", "hydraulic")
        props  = n.get("properties", {})

        cls = node_classes.get(ntype)
        if cls is None:
            print(f"  [AVISO] tipo desconhecido: {ntype!r} — ignorado")
            continue

        node = cls(nid, domain=domain, properties=props)

        # adiciona âncoras hidráulicas
        for aname in ANCHORS_BY_TYPE.get(ntype, []):
            anchor = node.add_anchor(aname, domain)
            anchor_index[(nid, aname)] = anchor

        nodes[nid] = node

    # ---- instancia conexões ----
    connections: list[Connection] = []
    for c in data["connections"]:
        src_nid    = c["source"]["node"]
        src_anchor = c["source"]["anchor"]
        tgt_nid    = c["target"]["node"]
        tgt_anchor = c["target"]["anchor"]

        a = anchor_index.get((src_nid, src_anchor))
        b = anchor_index.get((tgt_nid, tgt_anchor))

        if a is None or b is None:
            print(f"  [AVISO] conexão inválida: {src_nid}.{src_anchor} → {tgt_nid}.{tgt_anchor} — ignorada")
            continue

        conn = Connection(a, b)
        connections.append(conn)

    return nodes, connections


# ---------------------------------------------------------------------------
# Relatório de estado
# ---------------------------------------------------------------------------

SEP  = "═" * 70
SEP2 = "─" * 70

def _fmt(v):
    if isinstance(v, str):
        return v
    if v == 0.0:
        return "0"
    return f"{v:+.4e}"

def print_circuit_report(engine: SimulationEngine, step: int, dt: float):
    print(f"\n{SEP}")
    print(f"  PASSO {step:3d}  (t = {step * dt:.3f} s)")
    print(SEP)

    # ---- pressões por variável ----
    print("\n  ► VARIÁVEIS DE PRESSÃO (por âncora):")
    printed_pvars: set[str] = set()
    for node in engine.nodes.values():
        for aname, anchor in node.anchors.items():
            if anchor.domain != "hydraulic":
                continue
            pvar = getattr(anchor, "pressure_var", None)
            if pvar and pvar not in printed_pvars:
                printed_pvars.add(pvar)
                fault_tag = " ⚠ FAULT" if getattr(anchor, "fault", False) else ""
                press_tag = " ↑ PRESSURIZING" if getattr(anchor, "pressurizing", False) else ""
                print(f"    {pvar:50s} = {_fmt(anchor.pressure):>14} Pa{fault_tag}{press_tag}")

    # ---- estado por componente ----
    print(f"\n  ► COMPONENTES:")
    for node in engine.nodes.values():
        cls  = node.__class__.__name__
        nid  = node.id[:8]
        fault_tag = " ⚠ FAULT" if getattr(node, "fault", False) else ""
        print(f"\n    [{cls}] {nid}...{fault_tag}")

        # info específica por tipo
        if hasattr(node, "body_state"):
            state_label = "P→A" if node.body_state == 1 else "A→R" if hasattr(node, 'flow_var_out') else f"estado={node.body_state}"
            print(f"      corpo: {state_label}")
        if hasattr(node, "x") and hasattr(node, "stroke"):
            pct = node.x / node.stroke * 100 if node.stroke else 0
            print(f"      posição: {node.x:.4f} m  ({pct:.1f}% de {node.stroke} m stroke)")
        if hasattr(node, "p_set"):
            print(f"      p_set: {node.p_set:.2e} Pa")
        if hasattr(node, "Q_set"):
            print(f"      Q_set: {node.Q_set:.2e} m³/s")

        # âncoras
        for aname, anchor in node.anchors.items():
            if anchor.domain != "hydraulic":
                continue
            pval = _fmt(anchor.pressure)
            qval = _fmt(anchor.flow)
            arrow = ""
            if isinstance(anchor.flow, float):
                arrow = " →" if anchor.flow >= 0 else " ←"
            print(f"      porta {aname}: P = {pval:>14} Pa   Q = {qval:>14} m³/s{arrow}")

    # ---- balanço de vazão por nó de pressão ----
    print(f"\n  ► BALANÇO DE VAZÃO (por nó de pressão):")
    pvar_flows: dict[str, list[float]] = {}
    for node in engine.nodes.values():
        for aname, anchor in node.anchors.items():
            if anchor.domain != "hydraulic":
                continue
            pvar = getattr(anchor, "pressure_var", None)
            if not pvar:
                continue
            if pvar not in pvar_flows:
                pvar_flows[pvar] = []
            if isinstance(anchor.flow, float):
                pvar_flows[pvar].append(anchor.flow)

    all_balanced = True
    for pvar, flows in sorted(pvar_flows.items()):
        balance = sum(flows)
        ok = abs(balance) < 1e-9
        if not ok:
            all_balanced = False
        tag = "✓" if ok else f"✗ DESBALANCEADO ({balance:+.3e} m³/s)"
        print(f"    {pvar:50s}  Σ Q = {balance:+.4e} m³/s  {tag}")

    if all_balanced:
        print(f"\n  ✓ Todos os nós de pressão estão balanceados.")
    else:
        print(f"\n  ✗ Há desbalanceamento de vazão — circuito pode não ter convergido!")

    print(f"\n{SEP2}\n")


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def run(path: str, steps: int, dt: float, debug: bool, valve_state: str | None):
    print(f"\n{SEP}")
    print(f"  SIMULAÇÃO HEADLESS — {path}")
    print(SEP)

    nodes, connections = load_circuit(path)
    print(f"  Nós carregados    : {len(nodes)}")
    print(f"  Conexões carregadas: {len(connections)}")

    # aplica estado inicial de válvula se pedido
    if valve_state:
        side, nid_prefix = valve_state.split(":")
        for nid, node in nodes.items():
            if nid.startswith(nid_prefix) and hasattr(node, "bits"):
                node.bits[side] = 1
                print(f"  [override] válvula {nid[:8]}: bit '{side}' = 1")

    engine = SimulationEngine(nodes, connections, max_iterations=200)

    print(f"\n  Iniciando {steps} passo(s) com dt={dt} s...\n")

    for step in range(1, steps + 1):
        print(f"{'·' * 50}  passo {step}")
        try:
            engine.run_until_stable(dt=dt)
        except RuntimeError as e:
            print(f"\n  ✗ ERRO NO PASSO {step}: {e}")
            break

        print_circuit_report(engine, step, dt)

    print(f"\n  Simulação concluída.\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Simula um circuito hidráulico a partir de um JSON (sem PyQt)."
    )
    parser.add_argument("json_path", help="Caminho para o arquivo JSON do circuito")
    parser.add_argument("--steps", type=int, default=3,
                        help="Número de passos de simulação (default: 3)")
    parser.add_argument("--dt", type=float, default=0.05,
                        help="Delta de tempo por passo em segundos (default: 0.05)")
    parser.add_argument("--debug", action="store_true",
                        help="Ativa prints extras do solver")
    parser.add_argument("--valve", default=None,
                        help="Força bit de uma válvula: 'left:ID_PREFIX' ou 'right:ID_PREFIX'")
    args = parser.parse_args()

    run(args.json_path, args.steps, args.dt, args.debug, args.valve)


if __name__ == "__main__":
    main()
