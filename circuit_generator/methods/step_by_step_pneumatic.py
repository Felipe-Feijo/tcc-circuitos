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
  - Confirmação em série (sem AndValve) quando um átomo tem 2+ eventos

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

    # ── 4. Linhas de pressão e memórias por átomo ────────────────────────
    #
    #   Cada átomo (`_atomize`) ganha sua própria PressureLine dedicada e
    #   sua própria válvula de memória biestável (Valve_3_2_Ways com dois
    #   pilots pneumáticos) -- nunca compartilhadas entre átomos, ao
    #   contrário do cascata. Reset em anel: MC_k.PR vem da linha do
    #   PRÓXIMO átomo (módulo M), então o reset do último átomo vem da
    #   linha do átomo 0, fechando o anel sem caso especial. Só o botão
    #   seta MC_0 -- todas as outras memórias são setadas pela confirmação
    #   do átomo anterior (Task 4).

    atoms   = _atomize(events)
    n_atoms = len(atoms)

    pl_ids = [f"gen-pl-step{k}" for k in range(n_atoms)]
    mc_ids = [f"gen-mc-{k}" for k in range(n_atoms)]

    # O gerador de topologia não tem nenhuma posição de tela real pra
    # decidir quanto uma PressureLine precisa alcançar fisicamente -- só
    # quem sabe isso é a etapa de layout (step_by_step_layout.py, via
    # Grid.occupied_x_range). Aqui, cada PL nasce vazia e next_anchor()
    # cresce a lista sob demanda: exatamente 1 anchor por conexão real,
    # nunca mais, nunca menos, sem risco de esgotamento.
    pl_node_by_id: dict[str, dict] = {}
    for k, pl_id in enumerate(pl_ids):
        add_node(pl_id, "PressureLine", f"pressure_line_step:{k}",
                 properties={"anchors": []})
        pl_node_by_id[pl_id] = nodes[-1]

    _pl_counter: dict[str, int] = {pl_id: 0 for pl_id in pl_ids}

    def next_anchor(pl_id: str) -> str:
        idx = _pl_counter[pl_id] + 1
        _pl_counter[pl_id] = idx
        name = f"X{idx}"
        pl_node_by_id[pl_id]["properties"]["anchors"].append(name)
        return name

    for k in range(n_atoms):
        add_node(mc_ids[k], "Valve_3_2_Ways", f"memory:{k}",
                 properties={
                     "actuators": {
                         "left":  {"type": "pneumatic_pilot"},
                         "right": {"type": "pneumatic_pilot"},
                     },
                     "default_side": "left" if k == n_atoms - 1 else "right",
                 })
        ps_mc  = add_simple("PressureSource", f"pressure_source:mc-{k}")
        exh_mc = add_simple("Exhaust", f"exhaust:mc-{k}")
        connect(ps_mc, "P", mc_ids[k], "P")
        connect(mc_ids[k], "R", exh_mc, "R")
        connect(mc_ids[k], "A", pl_ids[k], next_anchor(pl_ids[k]))

    # Reset em anel: MC_k.PR ← linha do próximo átomo.
    for k in range(n_atoms):
        pr_source = pl_ids[(k + 1) % n_atoms]
        connect(pr_source, next_anchor(pr_source), mc_ids[k], "PR")

    # Única fonte de SET do átomo 0: o botão.
    connect("gen-btn", "A", mc_ids[0], "PL")

    # ── 5. Pilots das 4/2 alimentados direto pela linha do átomo ─────────
    #
    #   Cada evento do átomo aciona o pilot correspondente da sua 4/2
    #   direto da linha do átomo -- sem duplicação (um único tap por
    #   evento), inclusive quando o átomo é um bloco "(...)" com 2+
    #   eventos: a linha aceita quantos taps quiser, então alimentar 2+
    #   pilots ao mesmo tempo não exige nenhuma válvula extra (ao contrário
    #   do cascata, que precisa de fan_out/AndValve só pra isso).

    for k, atom in enumerate(atoms):
        pl_id = pl_ids[k]
        for e_idx, letter, direction in atom:
            v42_pilot = "PL" if direction == "+" else "PR"
            connect(pl_id, next_anchor(pl_id), f"gen-v42-{letter}", v42_pilot)

    # ── 6. Confirmação por átomo ────────────────────────────────────────
    #
    #   Cada átomo produz uma confirmação única (nunca duplicada -- ao
    #   contrário do cascata, aqui não existe fan_out: a sequência é plana,
    #   então todo átomo tem exatamente um "próximo"). Um evento sozinho
    #   usa uma única válvula de sinalização; um bloco de N>1 eventos usa N
    #   válvulas encadeadas em série -- a 1ª puxa P da linha do átomo, as
    #   demais puxam P da sig anterior (E lógico sem AndValve). A confirmação
    #   do átomo k seta MC_{k+1}.PL; a confirmação do último átomo fecha o
    #   ciclo alimentando btn.P (nunca MC_0.PL diretamente).

    def build_confirmation(k: int, atom: list[tuple[int, str, str]]) -> tuple[str, str]:
        pl_id = pl_ids[k]
        prev_output: tuple[str, str] | None = None
        for e_idx, letter, direction in atom:
            s_id   = f"gen-sig-{letter}-{'ext' if direction == '+' else 'ret'}-{e_idx}"
            s_role = f"signal_valve:{e_idx}"

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
            connect(add_simple("Exhaust", f"exhaust:sig-{e_idx}"), "R", s_id, "R")
            if prev_output is None:
                connect(pl_id, next_anchor(pl_id), s_id, "P")
            else:
                connect(prev_output[0], prev_output[1], s_id, "P")

            prev_output = (s_id, "A")

        return prev_output

    for k, atom in enumerate(atoms):
        final_id, final_anchor = build_confirmation(k, atom)
        if k == n_atoms - 1:
            connect(final_id, final_anchor, "gen-btn", "P")
        else:
            connect(final_id, final_anchor, mc_ids[k + 1], "PL")

    return {
        "version":     1,
        "nodes":       nodes,
        "connections": connections,
    }
