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
from circuit_generator.sequence_parser import extract_cylinders, split_into_groups

# Número de anchors reservados por atuador em cada PressureLine de grupo.
# 10 por cilindro garante folga para sig.P, pilots e entrada de memória.
_ANCHORS_PER_ACTUATOR = 10


def generate(events: list[tuple[str, str]]) -> dict:
    cylinders = extract_cylinders(events)
    groups    = split_into_groups(events)
    n_groups  = len(groups)
    n_cyls    = len(cylinders)

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

    def add_exhaust(role="exhaust"):
        uid = str(uuid.uuid4())
        add_node(uid, "Exhaust", role)
        return uid

    def add_ps(role="pressure_source"):
        uid = str(uuid.uuid4())
        add_node(uid, "PressureSource", role)
        return uid

    def connect(src_node, src_anchor, tgt_node, tgt_anchor):
        connections.append({
            "source": {"node": src_node, "anchor": src_anchor},
            "target": {"node": tgt_node, "anchor": tgt_anchor},
        })

    def sensor_ret(letter):  return f"{letter.lower()}0"
    def sensor_ext(letter):  return f"{letter.lower()}1"
    def confirm_sensor(letter, direction):
        return sensor_ext(letter) if direction == "+" else sensor_ret(letter)

    def sig_id(letter, direction):
        return f"gen-sig-{letter}-{'ext' if direction == '+' else 'ret'}"

    # ── 1. Cilindros ──────────────────────────────────────────────────────────

    for letter in cylinders:
        add_node(f"gen-cyl-{letter}", "DoubleActingCylinder", f"cylinder:{letter}",
                 properties={
                     "sensors": {
                         "retracted": {"type": "reed", "name": sensor_ret(letter)},
                         "extended":  {"type": "reed", "name": sensor_ext(letter)},
                     }
                 })

    # ── 2. Válvulas 4/2 com PS e Exhaust dedicados ───────────────────────────

    for letter in cylinders:
        add_node(f"gen-v42-{letter}", "Valve_4_2_Ways", f"main_valve:{letter}",
                 properties={
                     "actuators": {
                         "left":  {"type": "pilot"},
                         "right": {"type": "pilot"},
                     }
                 })
        connect(f"gen-v42-{letter}", "A", f"gen-cyl-{letter}", "A")
        connect(f"gen-v42-{letter}", "B", f"gen-cyl-{letter}", "B")

        exh_v42 = add_exhaust(f"exhaust:v42-{letter}-P")
        ps_v42  = add_ps(f"pressure_source:v42-{letter}-R")
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
    exh_btn = add_exhaust("exhaust:btn-R")
    connect(exh_btn, "R", "gen-btn", "R")

    # ── 4. Memórias (valve_5_2_ways) ─────────────────────────────────────────
    #
    # Indexação: mc[0] = mais baixo (recebe btn), mc[N-2] = mais alto
    # mem_ids[i] corresponde a mc[i]

    mem_ids = [f"gen-mc-{i}" for i in range(n_groups - 1)]
    n_mc    = len(mem_ids)

    for i, mem_id in enumerate(mem_ids):
        add_node(mem_id, "Valve_5_2_Ways", f"memory:{i}",
                 properties={
                     "actuators": {
                         "left":  {"type": "pilot"},
                         "right": {"type": "pilot"},
                     }
                 })
        exh1 = f"{mem_id}-exh-r1"
        exh2 = f"{mem_id}-exh-r2"
        add_node(exh1, "Exhaust", f"exhaust:{mem_id}-r1")
        add_node(exh2, "Exhaust", f"exhaust:{mem_id}-r2")
        connect(mem_id, "R1", exh1, "R")
        connect(mem_id, "R2", exh2, "R")

    # ── 5. Linhas de pressão de grupo ────────────────────────────────────────

    n_pl_anchors = n_cyls * _ANCHORS_PER_ACTUATOR
    all_anchors  = [f"X{i}" for i in range(1, n_pl_anchors + 1)]

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
                f"Aumente _ANCHORS_PER_ACTUATOR (atual={_ANCHORS_PER_ACTUATOR})."
            )
        return f"X{idx}"

    # ── 5b. Encadeamento de pressão ───────────────────────────────────────────
    #
    # Topologia cascata (mc[0]=mais baixo, mc[N-2]=mais alto, pl[0]=primeira):
    #
    #   btn.A    → mc[0].P
    #   mc[i].A  → mc[i+1].P          para i = 0..N-3
    #   mc[N-2].A → pl[0]             (mais alto alimenta primeira pl)
    #   mc[i].B  → pl[N-1-i]          mc[0].B→pl[N-1], mc[1].B→pl[N-2], ...
    #
    # Pilots:
    #   mc[0].PL  ← btn.A
    #   pl[i].Xi  → mc[N-2-i].PR      comuta mc correspondente
    #   pl[i].Xi  → mc[N-2-i-1].PL   seta mc abaixo para posição A (exceto i=N-2)

    if mem_ids:
        # mc[0].P ← PressureSource dedicado
        ps_mc = add_ps("pressure_source:mc0")
        connect(ps_mc, "P", mem_ids[0], "P")
        # mc[i].A → mc[i+1].P
        for i in range(n_mc - 1):
            connect(mem_ids[i], "A", mem_ids[i + 1], "P")
        # mc[N-2].A → pl[0]
        connect(mem_ids[-1], "A", pl_grp_ids[0], next_anchor(pl_grp_ids[0]))
        # mc[i].B → pl[N-1-i]
        for i, mem_id in enumerate(mem_ids):
            pl_idx = n_groups - 1 - i
            connect(mem_id, "B", pl_grp_ids[pl_idx], next_anchor(pl_grp_ids[pl_idx]))
        # mc[0].PL ← btn.A  (feito na seção 7)
    else:
        # 1 grupo: btn alimenta pl[0] direto
        connect("gen-btn", "A", pl_grp_ids[0], next_anchor(pl_grp_ids[0]))

    # ── 6. Válvulas de sinalização por evento ────────────────────────────────
    #
    # Arquitetura cascata correta:
    #
    #   Para cada grupo g com eventos [E0, E1, ..., En]:
    #     pl_grp[g] → v42-E0.pilot      (barramento aciona o 1º cilindro direto)
    #     pl_grp[g] → sig_E0.P          (sig_E0 confirma que E0 terminou)
    #     sig_E0.A  → v42-E1.pilot      (sig_E0 aciona o próximo)
    #     pl_grp[g] → sig_E1.P
    #     sig_E1.A  → v42-E2.pilot
    #     ...
    #     sig_En.A  → mc[g].PR          (última sig → troca de grupo)
    #               ou btn.P            (se for o último grupo → fecha ciclo)

    all_events_flat = [(g_idx, e_idx, letter, direction)
                       for g_idx, group in enumerate(groups)
                       for e_idx, (letter, direction) in enumerate(group)]

    for flat_idx, (g_idx, e_idx, letter, direction) in enumerate(all_events_flat):
        is_first_event = (e_idx == 0)
        is_last_event  = (e_idx == len(groups[g_idx]) - 1)
        is_last_group  = (g_idx == n_groups - 1)
        s_id           = sig_id(letter, direction)
        sensor         = confirm_sensor(letter, direction)
        v42_pilot      = "PL" if direction == "+" else "PR"
        pl_current     = pl_grp_ids[g_idx]

        # Primeiro evento do grupo: barramento aciona o cilindro diretamente
        if is_first_event:
            connect(pl_current, next_anchor(pl_current),
                    f"gen-v42-{letter}", v42_pilot)

        add_node(s_id, "Valve_3_2_Ways", f"signal_valve:{g_idx * 100 + e_idx}",
                 properties={
                     "actuators": {
                         "left":  {"type": "limit_switch", "sensor_name": sensor},
                         "right": {"type": "spring"},
                     }
                 })

        exh_sig = add_exhaust(f"exhaust:sig-{g_idx * 100 + e_idx}")
        connect(exh_sig, "R", s_id, "R")

        # Barramento alimenta a sig (todos os casos)
        connect(pl_current, next_anchor(pl_current), s_id, "P")

        if is_last_event and not is_last_group:
            # ── Última sig do grupo → mc.PR ──────────────────────────────────
            # A sig confirma o fim do último movimento do grupo e comuta a
            # memória correspondente: mc[n_mc - 1 - g_idx].PR
            connect(s_id, "A", mem_ids[n_mc - 1 - g_idx], "PR")

        elif is_last_event and is_last_group:
            # ── Última sig do último grupo → fecha ciclo ──────────────────────
            if mem_ids:
                connect(s_id, "A", "gen-btn", "P")

        else:
            # ── Evento normal: sig aciona o PRÓXIMO cilindro do grupo ─────────
            next_letter, next_dir = all_events_flat[flat_idx + 1][2:4]
            next_pilot = "PL" if next_dir == "+" else "PR"
            connect(s_id, "A", f"gen-v42-{next_letter}", next_pilot)

    # ── 7. Pilots PL/PR das memórias via PressureLines ───────────────────────
    #
    # pl[i] pilota mc[N-2-i].PR  (comuta para B → próxima pl ativa)
    # pl[i] também seta mc[N-2-i-1].PL (prepara mc abaixo para posição A)
    # exceto pl[N-2] que só pilota mc[0].PR (não há mc[-1])
    #
    # Esses connects usam next_anchor das pl correspondentes, e serão
    # reatribuídos pelo nearest-anchor da fase 3 do layout engine.
    # Pilots PL das memórias via pressure lines:
    #   mc[0].PL ← btn.A
    #   mc[i].PL ← pl[n_mc-i+1]   para i > 0
    #
    # Raciocínio: mc[i].B → pl[N-1-i], portanto a PL que ativa mc[i] de volta
    # (via PL) é a linha imediatamente abaixo (índice maior) = pl[N-1-i+1] = pl[N-i].
    # Com n_mc = N-1: pl[N-i] = pl[n_mc-i+1].
    # Pilots PR: conectados pelas sigs de fim de grupo (seção 6)
    if mem_ids:
        # mc[0].PL ← btn (sempre)
        connect("gen-btn", "A", mem_ids[0], "PL")
        # mc[i>0].PL ← pl[n_mc-i+1]
        for i, mem_id in enumerate(mem_ids):
            if i > 0:
                pl_pl_idx = n_mc - i + 1
                connect(pl_grp_ids[pl_pl_idx], next_anchor(pl_grp_ids[pl_pl_idx]),
                        mem_id, "PL")

    return {
        "version":     1,
        "nodes":       nodes,
        "connections": connections,
    }