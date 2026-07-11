"""
Gerador de circuito pelo método cascata (pneumático).

Topologia gerada para N grupos:
  - 1 pressure_source principal (alimenta memória e botão)
  - 1 button_switch (Valve_3_2_Ways com button + spring)
  - (N-1) válvulas de memória valve_5_2_ways encadeadas
  - N pressure_lines de grupo (barramentos com anchors por atuador)
  - Por cilindro: 1 double_acting_cylinder + 1 valve_4_2_ways (pilot+pilot)
                  + 1 PressureSource dedicado (porta R) + 1 Exhaust dedicado (porta P)
  - Por evento: 1 valve_3_2_ways de sinalização (limit_switch + spring)
                + 1 Exhaust dedicado (porta R)
  - Exhausts nas saídas R1, R2 de cada memória
  - 1 Exhaust dedicado na porta R do botão

Linhas de pressão de grupo:
  Cada PressureLine recebe (n_cyls * _ANCHORS_PER_ACTUATOR) anchors,
  numerados X1, X2, X3, ... sem lógica de "ala" ou "cauda".
  Um contador simples por pl_id fornece o próximo anchor livre em ordem crescente.

Fluxo de pressão principal:
  gen-ps → mc[-1].P  (pressão da fonte vai direto à última memória)
  mc.A → pl_grp[i]   (cada memória alimenta sua pl de grupo)
  mc[0].B → pl_grp[-1]  (grupo de retorno/repouso)

Sinalização:
  pl_grp.Xi → sig.P  (grupo alimenta sig — anchor consumido em ordem)
  sig.A → v42.PL/PR  (sinalização aciona cilindro)
  sig_transição.A → mc[g].PR  (transição de grupo)
  sig_fechamento.A → btn.P    (último sinal do ciclo → AND série com botão)
  btn.A → mc[0].PL            (botão aciona memória de start)

v42 pilots (via barramento):
  pl_grp[g_ext].Xi → v42.PL   (extensão: barramento do grupo onde A+ está)
  pl_grp[g_ret].Xi → v42.PR   (retração: barramento do grupo onde A- está)
"""

import uuid
from collections import Counter
from circuit_generator.sequence_parser import extract_cylinders, split_into_groups

# Anchors reservados por evento (aparição na sequência) por cilindro.
# 20 garante folga para sig.P, pilots e entrada de memória.
_ANCHORS_PER_EVENT = 20


def _atomize_group(group: list[tuple]) -> list[list[tuple[int, str, str]]]:
    """
    Agrupa os eventos de um grupo cascata em átomos: um evento sozinho vira
    um átomo de tamanho 1; eventos consecutivos com o mesmo parallel_id
    (bloco simultâneo) viram um átomo só. Cada evento é anotado com seu
    e_idx original dentro do grupo (necessário para nomear _role de
    válvulas de sinalização, que usa g_idx*100+e_idx).

    Espelha sequence_parser._atomize (mesma lógica de agrupamento por
    parallel_id), mas devolve e_idx junto — que sequence_parser não expõe
    porque não precisa dele para decidir corte de grupo.

    Aceita eventos de 2 ou 3 campos, (letra, direção) ou
    (letra, direção, parallel_id) — mesma tolerância usada em todo o
    módulo desde o sub-projeto 1.
    """
    atoms: list[list[tuple[int, str, str]]] = []
    i, n = 0, len(group)
    while i < n:
        letter, direction, *rest = group[i]
        pid = rest[0] if rest else None
        if pid is None:
            atoms.append([(i, letter, direction)])
            i += 1
            continue
        j = i
        atom: list[tuple[int, str, str]] = []
        while j < n:
            letter_j, direction_j, *rest_j = group[j]
            if (rest_j[0] if rest_j else None) != pid:
                break
            atom.append((j, letter_j, direction_j))
            j += 1
        atoms.append(atom)
        i = j
    return atoms


def generate(events: list[tuple[str, str]]) -> dict:
    cylinders = extract_cylinders(events)
    groups    = split_into_groups(events)
    n_groups  = len(groups)

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

    def add_simple(type_, role):
        uid = str(uuid.uuid4())
        add_node(uid, type_, role)
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

    # ── 1. Cilindros ──────────────────────────────────────────────────────────

    for letter in cylinders:
        add_node(f"gen-cyl-{letter}", "DoubleActingCylinder", f"cylinder:{letter}",
                 properties={
                     "sensors": {
                         "retracted": {"type": "reed", "name": f"{letter.lower()}0"},
                         "extended":  {"type": "reed", "name": f"{letter.lower()}1"},
                     },
                     "default_state": "extended" if starts_extended[letter] else "retracted",
                 })

    # ── 2. Válvulas 4/2 com PS e Exhaust dedicados ───────────────────────────

    for letter in cylinders:
        add_node(f"gen-v42-{letter}", "Valve_4_2_Ways", f"main_valve:{letter}",
                 properties={
                     "actuators": {
                         "left":  {"type": "pneumatic_pilot"},
                         "right": {"type": "pneumatic_pilot"},
                     },
                     "default_side": "left" if starts_extended[letter] else "right",
                 })
        connect(f"gen-v42-{letter}", "A", f"gen-cyl-{letter}", "A")
        connect(f"gen-v42-{letter}", "B", f"gen-cyl-{letter}", "B")

        exh_v42 = add_simple("Exhaust", f"exhaust:v42-{letter}-P")
        ps_v42  = add_simple("PressureSource", f"pressure_source:v42-{letter}-R")
        connect(exh_v42, "R", f"gen-v42-{letter}", "P")
        connect(ps_v42,  "P", f"gen-v42-{letter}", "R")

    # ── 3. Botão de início ───────────────────────────────────────────────────

    add_node("gen-btn", "Valve_3_2_Ways", "button",
             properties={
                 "actuators": {
                     "left":  {"type": "button"},
                     "right": {"type": "spring"},
                 }
             })
    connect(add_simple("Exhaust", "exhaust:btn-R"), "R", "gen-btn", "R")

    # ── 4. Memórias (valve_5_2_ways) ─────────────────────────────────────────
    # mem_ids[i] = mc[i]; mc[0] recebe btn, mc[N-2] é o mais alto.

    mem_ids = [f"gen-mc-{i}" for i in range(n_groups - 1)]
    n_mc    = len(mem_ids)

    for i, mem_id in enumerate(mem_ids):
        add_node(mem_id, "Valve_5_2_Ways", f"memory:{i}",
                 properties={
                     "actuators": {
                         "left":  {"type": "pneumatic_pilot"},
                         "right": {"type": "pneumatic_pilot"},
                     },
                     "default_side": "left" if i > 0 else "right",
                 })
        exh1, exh2 = f"{mem_id}-exh-r1", f"{mem_id}-exh-r2"
        add_node(exh1, "Exhaust", f"exhaust:{mem_id}-r1")
        add_node(exh2, "Exhaust", f"exhaust:{mem_id}-r2")
        connect(mem_id, "R1", exh1, "R")
        connect(mem_id, "R2", exh2, "R")

    # ── 5. Linhas de pressão de grupo ────────────────────────────────────────

    events_per_cyl = Counter(letter for letter, _, *__ in events)
    n_pl_anchors   = sum(events_per_cyl[c] * _ANCHORS_PER_EVENT for c in cylinders)
    all_anchors    = [f"X{i}" for i in range(1, n_pl_anchors + 1)]

    pl_grp_ids: list[str] = []
    _pl_counter: dict[str, int] = {}

    for g in range(n_groups):
        pl_id = f"gen-pl-grp{g + 1}"
        pl_grp_ids.append(pl_id)
        _pl_counter[pl_id] = 1
        add_node(pl_id, "PressureLine", f"pressure_line_group:{g}",
                 properties={"anchors": all_anchors.copy()})

    def next_anchor(pl_id: str) -> str:
        idx = _pl_counter[pl_id]
        _pl_counter[pl_id] = idx + 1
        if idx > n_pl_anchors:
            raise RuntimeError(
                f"PressureLine {pl_id} esgotou todos os {n_pl_anchors} anchors. "
                f"Aumente _ANCHORS_PER_EVENT (atual={_ANCHORS_PER_EVENT})."
            )
        return f"X{idx}"

    # ── 5b. Encadeamento de pressão ───────────────────────────────────────────
    #
    #   btn.A    → mc[0].P
    #   mc[i].A  → mc[i+1].P          para i = 0..N-3
    #   mc[N-2].A → pl[0]             (mais alto alimenta primeira pl)
    #   mc[i].B  → pl[N-1-i]          mc[0].B→pl[N-1], mc[1].B→pl[N-2], ...

    if mem_ids:
        connect(add_simple("PressureSource", "pressure_source:mc0"), "P", mem_ids[0], "P")
        for i in range(n_mc - 1):
            connect(mem_ids[i], "A", mem_ids[i + 1], "P")
        connect(mem_ids[-1], "A", pl_grp_ids[0], next_anchor(pl_grp_ids[0]))
        for i, mem_id in enumerate(mem_ids):
            pl_idx = n_groups - 1 - i
            connect(mem_id, "B", pl_grp_ids[pl_idx], next_anchor(pl_grp_ids[pl_idx]))
    else:
        # 1 grupo: btn alimenta pl[0] direto
        connect("gen-btn", "A", pl_grp_ids[0], next_anchor(pl_grp_ids[0]))

    # ── 6. Disparo e confirmação por átomo ───────────────────────────────────
    #
    #   Cada grupo cascata é dividido em "átomos" (_atomize_group): um
    #   evento sozinho, ou um bloco "(...)" inteiro (eventos com o mesmo
    #   parallel_id). Um átomo dispara cada um dos seus eventos exatamente
    #   uma vez (uma fonte dedicada por evento — nunca duplicada) e produz
    #   `fan_out` conjuntos de confirmação independentes: um por evento do
    #   PRÓXIMO átomo, ou 1 se for o último átomo do grupo (alimenta
    #   mc.PR/btn.P). Cada conjunto de confirmação é um grupo dedicado de
    #   válvulas de sinalização (mesmo sensor, mesmo P do barramento),
    #   encadeadas em série se o átomo tem mais de um evento -- a 1ª sig
    #   puxa P do barramento, as demais puxam P da saída (A) da sig
    #   anterior (E lógico sem nenhuma AndValve; ver spec
    #   docs/superpowers/specs/2026-07-11-serial-confirmation-no-andvalve-design.md).
    #
    #   fan_out é sempre uma consulta LOCAL ao próximo átomo apenas — nunca
    #   se acumula por trás de múltiplos átomos (só o disparo do átomo
    #   imediatamente anterior a um bloco precisa duplicar; o resto da
    #   cadeia serial antes dele permanece com um único conjunto).
    #
    #   Sem blocos "(...)", todo átomo tem tamanho 1 e fan_out=1 em todo
    #   lugar — o algoritmo colapsa exatamente na fiação evento-a-evento de
    #   antes deste sub-projeto.
    #
    #   Multi-ciclo (sub-projeto 2): quando o mesmo pilot de uma 4/2 recebe
    #   mais de uma fonte de disparo, as fontes são acumuladas em
    #   `triggers_for_pilot` e resolvidas na passada 2 (abaixo, inalterada)
    #   — 1 fonte conecta direto; 2+ fontes convergem via OrValve.

    triggers_for_pilot: dict[tuple[str, str], list[tuple[str, str]]] = {}

    flat_idx_of: dict[tuple[int, int], int] = {}
    _fi = 0
    for g_idx, group in enumerate(groups):
        for e_idx in range(len(group)):
            flat_idx_of[(g_idx, e_idx)] = _fi
            _fi += 1

    for g_idx, group in enumerate(groups):
        is_last_group = (g_idx == n_groups - 1)
        pl_current    = pl_grp_ids[g_idx]
        atoms         = _atomize_group(group)
        n_atoms       = len(atoms)

        entry_sources: list[tuple[str, str]] | None = None  # 1:1 com os eventos do átomo atual

        for atom_idx, atom in enumerate(atoms):
            is_last_atom = (atom_idx == n_atoms - 1)
            fan_out      = 1 if is_last_atom else len(atoms[atom_idx + 1])

            if entry_sources is None:
                entry_sources = [(pl_current, next_anchor(pl_current)) for _ in atom]

            # Dispara cada evento do átomo uma única vez.
            for slot_idx, (e_idx, letter, direction) in enumerate(atom):
                v42_pilot = "PL" if direction == "+" else "PR"
                triggers_for_pilot.setdefault((letter, v42_pilot), []).append(
                    entry_sources[slot_idx])

            # Produz `fan_out` conjuntos de confirmação independentes.
            group_outputs: list[tuple[str, str]] = []
            for conf_idx in range(fan_out):
                prev_output: tuple[str, str] | None = None
                for e_idx, letter, direction in atom:
                    suffix      = "" if fan_out == 1 else f"-{conf_idx}"
                    role_suffix = "" if fan_out == 1 else f":{conf_idx}"
                    s_id   = f"gen-sig-{letter}-{'ext' if direction == '+' else 'ret'}-{flat_idx_of[(g_idx, e_idx)]}{suffix}"
                    s_role = f"signal_valve:{g_idx * 100 + e_idx}{role_suffix}"

                    sig_default_side = "left" if (
                        (direction == "+" and     starts_extended[letter]) or
                        (direction == "-" and not starts_extended[letter])
                    ) else "right"

                    add_node(s_id, "Valve_3_2_Ways", s_role,
                             properties={
                                 "actuators": {
                                     "left":  {"type": "limit_switch", "sensor_name": confirm_sensor(letter, direction)},
                                     "right": {"type": "spring"},
                                 },
                                 "default_side": sig_default_side,
                             })
                    connect(add_simple("Exhaust", f"exhaust:sig-{g_idx * 100 + e_idx}{suffix}"), "R", s_id, "R")
                    if prev_output is None:
                        connect(pl_current, next_anchor(pl_current), s_id, "P")
                    else:
                        connect(prev_output[0], prev_output[1], s_id, "P")

                    prev_output = (s_id, "A")

                group_outputs.append(prev_output)

            if is_last_atom:
                final_id, final_anchor = group_outputs[0]
                if not is_last_group:
                    connect(final_id, final_anchor, mem_ids[n_mc - 1 - g_idx], "PR")
                elif mem_ids:
                    connect(final_id, final_anchor, "gen-btn", "P")
            else:
                entry_sources = group_outputs

    # ── 6b. Resolve as fontes de disparo acumuladas por pilot ────────────────
    #
    #   1 fonte  -> conecta direto no pilot, na mesma ordem de chamada de
    #               connect() usada antes deste sub-projeto (preserva a
    #               topologia exata para sequências de 1 ciclo por cilindro).
    #   2+ fontes -> cadeia binária de OrValve: a saída de cada OR alimenta
    #               a entrada livre da próxima, até a última OR alimentar o
    #               pilot da 4/2.

    for (letter, pilot_side), sources in triggers_for_pilot.items():
        if len(sources) == 1:
            src_id, src_anchor = sources[0]
            if src_anchor == "A":
                # fonte encadeada (sig.A) -> pilot da 4/2
                connect(src_id, src_anchor, f"gen-v42-{letter}", pilot_side)
            else:
                # fonte direta do barramento -> pilot da 4/2 (a 4/2 é o
                # "source" da chamada, o barramento é o "target" — mesma
                # ordem usada antes deste sub-projeto)
                connect(f"gen-v42-{letter}", pilot_side, src_id, src_anchor)
        else:
            current = sources[0]
            for i, nxt in enumerate(sources[1:]):
                or_id = add_simple("OrValve", f"or_valve:{letter}:{pilot_side}:{i}")
                connect(current[0], current[1], or_id, "X")
                connect(nxt[0], nxt[1], or_id, "Y")
                current = (or_id, "A")
            connect(current[0], current[1], f"gen-v42-{letter}", pilot_side)

    # ── 7. Pilots PL das memórias via PressureLines ──────────────────────────
    #
    #   mc[0].PL ← btn.A
    #   mc[i].PL ← pl[n_mc-i+1]   para i > 0

    if mem_ids:
        connect("gen-btn", "A", mem_ids[0], "PL")
        for i, mem_id in enumerate(mem_ids):
            if i > 0:
                pl_pl_idx = n_mc - i + 1
                connect(mem_id, "PL",
                        pl_grp_ids[pl_pl_idx], next_anchor(pl_grp_ids[pl_pl_idx]))

    return {
        "version":     1,
        "nodes":       nodes,
        "connections": connections,
    }