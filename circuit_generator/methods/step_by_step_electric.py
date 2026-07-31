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
  - Por átomo: 1 RelayCoil K_k + 3 RelaySwitch de degrau (ramo A: sensor(es)
    de fim de curso do átomo anterior em série + contato do K do átomo
    anterior; ramo B: self-hold do próprio K_k; reset: NC do K do próximo
    átomo) -- anel de lógica, ver docs/superpowers/specs/
    2026-07-31-step-by-step-electric-power-contacts-design.md
  - Por (cilindro, direção) presente na sequência: 1 SolenoidCoil Y
    (sensor "Y{letra}{1|0}") + 1 contato de potência NO dedicado por átomo
    que dispara aquele movimento (relay_sensor = K do átomo), todos em
    paralelo alimentando a mesma bobina Y -- multi-ciclo vira só mais um
    contato em paralelo, sem sig nem OrValve.
  - Pilotagem da 4/2: atuador "solenoid" sempre, lendo direto o Y do
    (cilindro, direção) correspondente.

Anel de lógica (auto-mantido, self-holding):
  VoltageSource --> [sensor(s) fim de curso átomo k-1] --> [K_{k-1} NO] --\
  VoltageSource --> [K_k NO self-hold] -------------------------------------+--> [K_{k+1} NC] --> K_k --> Ground
  (só o átomo M-1) VoltageSource --> [botão NO] -----------------------/
  (só o átomo 0) VoltageSource --> [K_último NO] --> [botão de início NO] --/

Zona de potência (independente por (cilindro, direção)):
  VoltageSource --> [K_k1 NO] --\
  VoltageSource --> [K_k2 NO] ----+--> Y_{letra}{dir} --> Ground   (k1, k2, ... = átomos que disparam esse movimento)

Diferente do pneumático: não há PressureLine nem memória 3/2 -- o "passo
ativo" é lembrado pelo próprio estado energizado/desenergizado dos K_k.
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

    def power_sensor(letter, direction):
        return f"Y{letter}{'1' if direction == '+' else '0'}"

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
    #      aqui -- preenchidos na seção 6, "zona de potência") ────────────

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
    add_node("gen-btn-start", "ButtonSwitch", "button_start", domain="electric",
             properties={"contact_type": "NO"})

    _bus_counter: dict[str, int] = {"gen-vsource": 0, "gen-ground": 0}

    def next_bus_anchor(bus_id: str) -> str:
        idx = _bus_counter[bus_id] + 1
        _bus_counter[bus_id] = idx
        name = f"X{idx}"
        bus_node = next(n for n in nodes if n["id"] == bus_id)
        bus_node["properties"]["anchors"].append(name)
        return name

    # ── 4. Anel de bobinas K_k (uma por átomo) e degraus self-holding ────
    #
    #   Cada átomo ganha exatamente 1 RelayCoil (K_k, sensor "K{k+1}",
    #   1-indexado) e um degrau de 3 grupos de contatos RelaySwitch:
    #     - ramo A (partida): cadeia serial de contatos NO lendo os
    #       sensores de fim de curso do átomo ANTERIOR (1 contato por
    #       evento do átomo, em série -- mesma técnica de confirmação
    #       serial já usada no pneumático), seguida de 1 contato NO do K do
    #       átomo anterior.
    #     - ramo B (self-hold): 1 contato NO do próprio K_k, em paralelo
    #       com o ramo A.
    #     - reset: 1 contato NC do K do PRÓXIMO átomo (módulo M -- fecha o
    #       anel sem caso especial), depois do ponto onde ramo A e ramo B
    #       convergem.
    #   O átomo M-1 (último do ciclo) ganha um terceiro ramo em paralelo,
    #   só com o ButtonSwitch de bootstrap.
    #
    #   K_k é um relé de LÓGICA só -- não aciona nada pneumático
    #   diretamente. A bobina de potência (Y, seção 6) é um componente
    #   físico separado, acionado por um contato NO dedicado de K_k.

    k_ids = [f"gen-coil-{k}" for k in range(n_atoms)]
    for k in range(n_atoms):
        add_node(k_ids[k], "RelayCoil", f"coil:{k}", domain="electric",
                 properties={"sensor": {"coil": {"name": f"K{k + 1}"}}})

    def contact(role_suffix: str, contact_type: str, relay_sensor: str) -> str:
        cid = f"gen-contact-{role_suffix}"
        add_node(cid, "RelaySwitch", f"contact:{role_suffix}", domain="electric",
                 properties={"contact_type": contact_type, "relay_sensor": relay_sensor})
        return cid

    for k in range(n_atoms):
        prev_k    = (k - 1) % n_atoms
        next_k    = (k + 1) % n_atoms
        prev_atom = atoms[prev_k]

        # Ramo A: cadeia serial de contatos de sensor + contato do K anterior.
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

        ramo_a_prev_contact = contact(f"{k}-ramo_a_prev", "NO", f"K{prev_k + 1}")
        connect(chain_prev_output[0], chain_prev_output[1], ramo_a_prev_contact, "T")

        # Ramo B: self-hold do próprio K_k.
        ramo_b_contact = contact(f"{k}-ramo_b_self", "NO", f"K{k + 1}")

        # A fonte alimenta o início de cada ramo (2 taps em paralelo).
        connect("gen-vsource", next_bus_anchor("gen-vsource"), first_sensor_contact, "T")
        connect("gen-vsource", next_bus_anchor("gen-vsource"), ramo_b_contact, "T")

        # Os dois ramos convergem no contato de reset (NC do próximo K).
        reset_contact = contact(f"{k}-reset_nc", "NC", f"K{next_k + 1}")

        # Botão de início do ciclo: só o PRIMEIRO átomo, em série no fim do
        # ramo A (depois do contato do K anterior, antes de convergir com o
        # ramo B) -- K0 só energiza se sensor(es) + K_último + este botão
        # estiverem todos fechados, dando controle manual exato de quando o
        # ciclo começa (em vez de K0 disparar sozinho assim que sensor+K
        # ficarem satisfeitos automaticamente).
        if k == 0:
            connect(ramo_a_prev_contact, "B", "gen-btn-start", "T")
            connect("gen-btn-start", "B", reset_contact, "T")
        else:
            connect(ramo_a_prev_contact, "B", reset_contact, "T")
        connect(ramo_b_contact, "B", reset_contact, "T")

        # Bootstrap: só o último átomo do ciclo ganha o ramo do botão.
        if k == n_atoms - 1:
            connect("gen-vsource", next_bus_anchor("gen-vsource"), "gen-btn", "T")
            connect("gen-btn", "B", reset_contact, "T")

        connect(reset_contact, "B", k_ids[k], "T")
        connect(k_ids[k], "B", "gen-ground", next_bus_anchor("gen-ground"))

    # ── 5. Agrupamento por (cilindro, direção): quais átomos disparam
    #      cada movimento -- mesmo mapa usado pelo pneumático/cascata pra
    #      multi-ciclo, aqui vira a lista de contatos de potência em
    #      paralelo de cada bobina Y ──────────────────────────────────────

    triggers_for_pilot: dict[tuple[str, str], list[int]] = {}
    for k, atom in enumerate(atoms):
        for e_idx, letter, direction in atom:
            triggers_for_pilot.setdefault((letter, direction), []).append(k)

    # ── 6. Zona de potência: 1 bobina Y por (cilindro, direção) + 1
    #      contato de potência NO dedicado por átomo que dispara aquele
    #      movimento, todos em paralelo alimentando a mesma bobina ───────
    #
    #   Multi-ciclo (2+ átomos disparando o mesmo (letra, direção)) vira
    #   só mais um contato em paralelo, sem nenhum componente de
    #   convergência dedicado -- o barramento elétrico já suporta múltiplas
    #   conexões no mesmo anchor (AnchorItem.connections é uma lista, não
    #   um slot único). A 4/2 sempre pilota via atuador "solenoid" lendo o
    #   Y correspondente -- nenhuma ramificação de caso único vs multi-ciclo.

    for (letter, direction), atom_indexes in triggers_for_pilot.items():
        pilot_anchor = "PL" if direction == "+" else "PR"
        side = "left" if pilot_anchor == "PL" else "right"
        v42 = v42_node_by_letter[letter]
        dir_tag = "ext" if direction == "+" else "ret"

        y_sensor_name = power_sensor(letter, direction)
        y_id = f"gen-ycoil-{letter}-{dir_tag}"
        add_node(y_id, "SolenoidCoil", f"power_coil:{letter}:{direction}", domain="electric",
                 properties={"sensor": {"coil": {"name": y_sensor_name}}})

        for k in atom_indexes:
            power_contact = contact(f"power-{letter}-{dir_tag}-{k}", "NO", f"K{k + 1}")
            connect("gen-vsource", next_bus_anchor("gen-vsource"), power_contact, "T")
            connect(power_contact, "B", y_id, "T")

        connect(y_id, "B", "gen-ground", next_bus_anchor("gen-ground"))

        v42["properties"]["actuators"][side] = {
            "type": "solenoid", "sensor_name": y_sensor_name,
        }

    return {
        "version":     1,
        "nodes":       nodes,
        "connections": connections,
    }
