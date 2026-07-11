"""
Gerador de circuito pelo método passo a passo pneumático.

Topologia gerada para uma sequência com M átomos (mesmo conceito de átomo
usado em circuit_generator.methods.cascade: um evento sozinho, ou um bloco
"(...)" inteiro de movimentos simultâneos):
  - 1 button_switch (Valve_3_2_Ways com button + spring)
  - Por cilindro: 1 double_acting_cylinder + 1 valve_4_2_ways (pilot+pilot)
                  + 1 PressureSource dedicado (porta R) + 1 Exhaust dedicado (porta P)
  - Por átomo: 1 PressureLine dedicada + 1 valve_3_2_ways de memória
               biestável (pilot+pilot) com PressureSource dedicada (porta P)
               e Exhaust dedicado (porta R)
  - Por evento: 1 valve_3_2_ways de sinalização (limit_switch + spring)
                + 1 Exhaust dedicado (porta R)
  - AndValve mesclando confirmações quando um átomo tem 2+ eventos

Diferente do cascata: não há grupos nem alternância de memória A/B -- cada
átomo tem sua própria linha e memória dedicadas, nunca reaproveitadas.
Ver docs/superpowers/specs/2026-07-10-step-by-step-pneumatic-design.md.

Fluxo de pressão principal (anel):
  MC_k.A → gen-pl-step{k}
  gen-pl-step{k} → MC_{k-1 mod M}.PR     (reset em anel)
  btn.A → MC_0.PL                        (única fonte de SET do átomo 0)
  confirmação(átomo k-1) → MC_k.PL       (SET dos demais átomos)
  confirmação(átomo M-1) → btn.P         (fechamento do ciclo)

Pilots dos v42 (via linha do próprio átomo, sem duplicação):
  gen-pl-step{k} → v42.PL/PR             (um tap por evento do átomo)

Multi-ciclo (mesma letra+direção repetida em átomos não-adjacentes) não é
suportado -- ver `_check_no_multi_cycle` e a seção "Fora de escopo" do spec.
"""

import uuid
from circuit_generator.sequence_parser import extract_cylinders

_ANCHORS_PER_ATOM = 20


def _atomize(events: list[tuple]) -> list[list[tuple[int, str, str]]]:
    """Agrupa os eventos da sequência inteira em átomos: eventos consecutivos
    com o mesmo parallel_id (3º campo) formam um átomo; os demais viram
    átomos de 1 evento. Cada evento é anotado com seu índice original na
    sequência (flat_idx).

    Mesma lógica de circuit_generator.sequence_parser._atomize e de
    circuit_generator.methods.cascade._atomize_group, reimplementada aqui
    porque o passo a passo não tem camada de grupos -- é uma sequência
    plana de átomos, sem o corte por repetição de letra que o cascata usa
    para dividir grupos.

    Aceita eventos de 2 ou 3 campos, (letra, direção) ou
    (letra, direção, parallel_id).
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


def _check_no_multi_cycle(events: list[tuple]) -> None:
    """Multi-ciclo (mesma letra+direção repetida em átomos não-adjacentes)
    ainda não é suportado neste método -- ver spec, seção "Fora de escopo".
    Levanta um erro claro em vez de gerar uma topologia fisicamente
    incorreta (2 fontes de disparo diretas no mesmo pilot da 4/2, sem
    OrValve para convergi-las)."""
    seen: set[tuple[str, str]] = set()
    for letter, direction, *_ in events:
        key = (letter, direction)
        if key in seen:
            raise NotImplementedError(
                f"Multi-ciclo não suportado: cilindro '{letter}' repete a "
                f"direção '{direction}' em pontos não-adjacentes da "
                f"sequência. Isso exigiria convergência via OrValve, fora "
                f"do escopo deste método por enquanto."
            )
        seen.add(key)


def generate(events: list[tuple[str, str]]) -> dict:
    _check_no_multi_cycle(events)
    cylinders = extract_cylinders(events)

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

    # ── 1. Cilindros ─────────────────────────────────────────────────────

    for letter in cylinders:
        add_node(f"gen-cyl-{letter}", "DoubleActingCylinder", f"cylinder:{letter}",
                 properties={
                     "sensors": {
                         "retracted": {"type": "reed", "name": f"{letter.lower()}0"},
                         "extended":  {"type": "reed", "name": f"{letter.lower()}1"},
                     },
                     "default_state": "extended" if starts_extended[letter] else "retracted",
                 })

    # ── 2. Válvulas 4/2 com PS e Exhaust dedicados ──────────────────────

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

    # ── 3. Botão de início ───────────────────────────────────────────────

    add_node("gen-btn", "Valve_3_2_Ways", "button",
             properties={
                 "actuators": {
                     "left":  {"type": "button"},
                     "right": {"type": "spring"},
                 }
             })
    connect(add_simple("Exhaust", "exhaust:btn-R"), "R", "gen-btn", "R")

    return {
        "version":     1,
        "nodes":       nodes,
        "connections": connections,
    }
