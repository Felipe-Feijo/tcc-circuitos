"""
Gerador de circuito pelo método passo a passo elétrico.

Topologia gerada para uma sequência com M átomos (mesmo conceito de átomo
usado em circuit_generator.methods.step_by_step_pneumatic: um evento
sozinho, ou um bloco "(...)" inteiro de movimentos simultâneos):
  - 1 VoltageSource + 1 Ground (barramentos elétricos, anchors crescem sob
    demanda, mesmo padrão do PressureLine pneumático)
  - 1 ButtonSwitch de bootstrap do ciclo
  - Por cilindro: 1 DoubleActingCylinder + 1 Valve_4_2_Ways (P/R com
    PressureSource/Exhaust dedicados, igual ao pneumático)
  - Por átomo: 1 SolenoidCoil Y_k + 3 RelaySwitch de degrau (ramo A: sensor(es)
    de fim de curso do átomo anterior em série + contato do Y do átomo
    anterior; ramo B: self-hold do próprio Y_k; reset: NC do Y do próximo
    átomo) -- ver docs/superpowers/specs/2026-07-30-step-by-step-electric-design.md
  - Pilotagem da 4/2: atuador "solenoid" direto (ocorrência única) ou sig +
    OrValve (multi-ciclo) -- ver Task 3 / seção "pilotagem" abaixo.

Anel elétrico (auto-mantido, self-holding):
  VoltageSource --> [sensor(s) fim de curso átomo k-1] --> [Y_{k-1} NO] --\
  VoltageSource --> [Y_k NO self-hold] -------------------------------------+--> [Y_{k+1} NC] --> Y_k --> Ground
  (só o átomo M-1) VoltageSource --> [botão NO] -----------------------/

Diferente do pneumático: não há PressureLine nem memória 3/2 -- o "passo
ativo" é lembrado pelo próprio estado energizado/desenergizado dos Y_k.
"""

import uuid
from circuit_generator.sequence_parser import extract_cylinders


def _atomize(events: list[tuple]) -> list[list[tuple[int, str, str]]]:
    """Agrupa os eventos da sequência inteira em átomos: eventos consecutivos
    com o mesmo parallel_id (3º campo) formam um átomo; os demais viram
    átomos de 1 evento. Cada evento é anotado com seu índice original na
    sequência (flat_idx).

    Reimplementado aqui (não compartilhado com
    step_by_step_pneumatic._atomize) -- mesmo princípio adotado em todo o
    resto do gerador para essa função utilitária.
    """
    atoms: list[list[tuple[int, str, str]]] = []
    i, n = 0, len(events)
    while i < n:
        letter, direction, *rest = events[i]
        pid = rest[0] if rest else None
        if pid is None:
            atoms.append([(i, letter, direction)])
            i += 1
            continue
        j = i
        atom: list[tuple[int, str, str]] = []
        while j < n:
            letter_j, direction_j, *rest_j = events[j]
            if (rest_j[0] if rest_j else None) != pid:
                break
            atom.append((j, letter_j, direction_j))
            j += 1
        atoms.append(atom)
        i = j
    return atoms


def generate(events: list[tuple[str, str]]) -> dict:
    cylinders = extract_cylinders(events)

    atoms   = _atomize(events)
    n_atoms = len(atoms)

    if n_atoms < 3:
        raise ValueError(
            f"step_by_step_electric requer pelo menos 3 átomos no anel de relés "
            f"(sequência gerou {n_atoms})."
        )

    nodes       = []
    connections = []

    def add_node(id_, type_, role, domain="pneumatic", properties=None, **extra):
        n = {
            "id":         id_,
            "type":       type_,
            "domain":     domain,
            "position":   {"x": 0, "y": 0},
            "properties": properties or {},
            "labels":     {},
            "_role":      role,
        }
        n.update(extra)
        nodes.append(n)
        return n

    def add_simple(type_, role, domain="pneumatic"):
        uid = str(uuid.uuid4())
        add_node(uid, type_, role, domain=domain)
        return uid

    def connect(src_node, src_anchor, tgt_node, tgt_anchor):
        connections.append({
            "source": {"node": src_node, "anchor": src_anchor},
            "target": {"node": tgt_node, "anchor": tgt_anchor},
        })

    def confirm_sensor(letter, direction):
        return f"{letter.lower()}{'1' if direction == '+' else '0'}"

    # Estado inicial: se o primeiro movimento for "-", o cilindro começa estendido.
    first_event     = {letter: direction for letter, direction, *_ in reversed(events)}
    starts_extended = {letter: first_event[letter] == "-" for letter in cylinders}

    # ── 1. Cilindros (idêntico ao pneumático) ────────────────────────────

    for letter in cylinders:
        add_node(f"gen-cyl-{letter}", "DoubleActingCylinder", f"cylinder:{letter}",
                 properties={
                     "sensors": {
                         "retracted": {"type": "reed", "name": f"{letter.lower()}0"},
                         "extended":  {"type": "reed", "name": f"{letter.lower()}1"},
                     },
                     "default_state": "extended" if starts_extended[letter] else "retracted",
                 })

    # ── 2. Válvulas 4/2 com PS e Exhaust dedicados (atuadores ficam vazios
    #      aqui -- preenchidos na seção de pilotagem, Task 3) ─────────────

    v42_node_by_letter: dict[str, dict] = {}
    for letter in cylinders:
        v42 = add_node(f"gen-v42-{letter}", "Valve_4_2_Ways", f"main_valve:{letter}",
                        properties={
                            "actuators": {},
                            "default_side": "left" if starts_extended[letter] else "right",
                        })
        v42_node_by_letter[letter] = v42
        connect(f"gen-v42-{letter}", "A", f"gen-cyl-{letter}", "A")
        connect(f"gen-v42-{letter}", "B", f"gen-cyl-{letter}", "B")

        exh_v42 = add_simple("Exhaust", f"exhaust:v42-{letter}-P")
        ps_v42  = add_simple("PressureSource", f"pressure_source:v42-{letter}-R")
        connect(exh_v42, "R", f"gen-v42-{letter}", "P")
        connect(ps_v42,  "P", f"gen-v42-{letter}", "R")

    # ── 3. Barramentos elétricos (fonte, terra) e botão de bootstrap ─────

    add_node("gen-vsource", "VoltageSource", "voltage_source", domain="electric",
             properties={"anchors": []})
    add_node("gen-ground", "Ground", "ground", domain="electric",
             properties={"anchors": []})
    add_node("gen-btn", "ButtonSwitch", "button", domain="electric",
             properties={"contact_type": "NO"})

    _bus_counter: dict[str, int] = {"gen-vsource": 0, "gen-ground": 0}

    def next_bus_anchor(bus_id: str) -> str:
        idx = _bus_counter[bus_id] + 1
        _bus_counter[bus_id] = idx
        name = f"X{idx}"
        bus_node = next(n for n in nodes if n["id"] == bus_id)
        bus_node["properties"]["anchors"].append(name)
        return name

    # ── 4. Anel de bobinas Y_k (uma por átomo) e degraus self-holding ────
    #
    #   Cada átomo ganha exatamente 1 SolenoidCoil (Y_k, sensor "Y{k+1}",
    #   1-indexado) e um degrau de 3 grupos de contatos RelaySwitch:
    #     - ramo A (partida): cadeia serial de contatos NO lendo os
    #       sensores de fim de curso do átomo ANTERIOR (1 contato por
    #       evento do átomo, em série -- mesma técnica de confirmação
    #       serial já usada no pneumático), seguida de 1 contato NO do Y do
    #       átomo anterior.
    #     - ramo B (self-hold): 1 contato NO do próprio Y_k, em paralelo
    #       com o ramo A.
    #     - reset: 1 contato NC do Y do PRÓXIMO átomo (módulo M -- fecha o
    #       anel sem caso especial), depois do ponto onde ramo A e ramo B
    #       convergem.
    #   O átomo M-1 (último do ciclo) ganha um terceiro ramo em paralelo,
    #   só com o ButtonSwitch de bootstrap.

    y_ids = [f"gen-coil-{k}" for k in range(n_atoms)]
    for k in range(n_atoms):
        add_node(y_ids[k], "SolenoidCoil", f"coil:{k}", domain="electric",
                 properties={"sensor": {"coil": {"name": f"Y{k + 1}"}}})

    def contact(role_suffix: str, contact_type: str, relay_sensor: str) -> str:
        cid = f"gen-contact-{role_suffix}"
        add_node(cid, "RelaySwitch", f"contact:{role_suffix}", domain="electric",
                 properties={"contact_type": contact_type, "relay_sensor": relay_sensor})
        return cid

    for k in range(n_atoms):
        prev_k    = (k - 1) % n_atoms
        next_k    = (k + 1) % n_atoms
        prev_atom = atoms[prev_k]

        # Ramo A: cadeia serial de contatos de sensor + contato do Y anterior.
        chain_prev_output: tuple[str, str] | None = None
        first_sensor_contact: str | None = None
        for i, (e_idx, letter, direction) in enumerate(prev_atom):
            sensor_name = confirm_sensor(letter, direction)
            cid = contact(f"{k}-ramo_a_sensor{i}", "NO", sensor_name)
            if first_sensor_contact is None:
                first_sensor_contact = cid
            if chain_prev_output is not None:
                connect(chain_prev_output[0], chain_prev_output[1], cid, "T")
            chain_prev_output = (cid, "B")

        ramo_a_prev_contact = contact(f"{k}-ramo_a_prev", "NO", f"Y{prev_k + 1}")
        connect(chain_prev_output[0], chain_prev_output[1], ramo_a_prev_contact, "T")

        # Ramo B: self-hold do próprio Y_k.
        ramo_b_contact = contact(f"{k}-ramo_b_self", "NO", f"Y{k + 1}")

        # A fonte alimenta o início de cada ramo (2 taps em paralelo).
        connect("gen-vsource", next_bus_anchor("gen-vsource"), first_sensor_contact, "T")
        connect("gen-vsource", next_bus_anchor("gen-vsource"), ramo_b_contact, "T")

        # Os dois ramos convergem no contato de reset (NC do próximo Y).
        reset_contact = contact(f"{k}-reset_nc", "NC", f"Y{next_k + 1}")
        connect(ramo_a_prev_contact, "B", reset_contact, "T")
        connect(ramo_b_contact, "B", reset_contact, "T")

        # Bootstrap: só o último átomo do ciclo ganha o ramo do botão.
        if k == n_atoms - 1:
            connect("gen-vsource", next_bus_anchor("gen-vsource"), "gen-btn", "T")
            connect("gen-btn", "B", reset_contact, "T")

        connect(reset_contact, "B", y_ids[k], "T")
        connect(y_ids[k], "B", "gen-ground", next_bus_anchor("gen-ground"))

    # ── 5. Pilotagem das 4/2: solenoid direto (ocorrência única) ou sig +
    #      OrValve encadeada (multi-ciclo) ─────────────────────────────
    #
    #   Reaproveita o algoritmo de duas passadas já usado pelo pneumático
    #   pra multi-ciclo (ver docs/superpowers/specs/
    #   2026-07-12-step-by-step-multi-cycle-or-valve-design.md), com duas
    #   diferenças: a "fonte" de cada sig é um PressureSource dedicado (não
    #   um tap de PressureLine, que não existe mais aqui) e o atuador da
    #   sig é "solenoid" (lê o Y_k do átomo daquela ocorrência) em vez de
    #   "limit_switch".

    triggers_for_pilot: dict[tuple[str, str], list[int]] = {}
    for k, atom in enumerate(atoms):
        for e_idx, letter, direction in atom:
            triggers_for_pilot.setdefault((letter, direction), []).append(k)

    for (letter, direction), atom_indexes in triggers_for_pilot.items():
        pilot_anchor = "PL" if direction == "+" else "PR"
        side = "left" if pilot_anchor == "PL" else "right"
        v42 = v42_node_by_letter[letter]

        if len(atom_indexes) == 1:
            k = atom_indexes[0]
            v42["properties"]["actuators"][side] = {
                "type": "solenoid", "sensor_name": f"Y{k + 1}",
            }
            continue

        v42["properties"]["actuators"][side] = {"type": "pneumatic_pilot"}

        sig_outputs: list[tuple[str, str]] = []
        for k in atom_indexes:
            dir_tag = "ext" if direction == "+" else "ret"
            sig_id = f"gen-pilot-sig-{letter}-{dir_tag}-{k}"
            add_node(sig_id, "Valve_3_2_Ways", f"pilot_sig:{letter}:{direction}:{k}",
                     properties={
                         "actuators": {
                             "left":  {"type": "solenoid", "sensor_name": f"Y{k + 1}"},
                             "right": {"type": "spring"},
                         },
                         "default_side": "right",
                     })
            ps  = add_simple("PressureSource", f"pressure_source:pilot-sig-{letter}-{direction}-{k}")
            exh = add_simple("Exhaust", f"exhaust:pilot-sig-{letter}-{direction}-{k}")
            connect(ps, "P", sig_id, "P")
            connect(sig_id, "R", exh, "R")
            sig_outputs.append((sig_id, "A"))

        # Mesma convenção de lateralidade X/Y da OrValve usada no
        # pneumático: no lado PL a cadeia cresce pra esquerda do cilindro
        # (prev entra em X), no lado PR cresce pra direita (prev entra em Y).
        prev_anchor_name, new_anchor_name = ("X", "Y") if pilot_anchor == "PL" else ("Y", "X")

        prev_id, prev_anchor = sig_outputs[0]
        for i in range(1, len(sig_outputs)):
            or_id = add_simple("OrValve", f"or_valve:{letter}:{pilot_anchor}:{i - 1}")
            connect(prev_id, prev_anchor, or_id, prev_anchor_name)
            src_id, src_anchor = sig_outputs[i]
            connect(src_id, src_anchor, or_id, new_anchor_name)
            prev_id, prev_anchor = or_id, "A"
        connect(prev_id, prev_anchor, v42["id"], pilot_anchor)

    return {
        "version":     1,
        "nodes":       nodes,
        "connections": connections,
    }
