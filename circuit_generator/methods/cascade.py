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

    # ── 3. Infraestrutura principal ──────────────────────────────────────────

    add_node("gen-ps", "PressureSource", "pressure_source")

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

    mem_ids = [f"gen-mc-grp{i+1}-grp{i+2}" for i in range(n_groups - 1)]

    for mem_id in mem_ids:
        add_node(mem_id, "Valve_5_2_Ways", f"memory:{mem_ids.index(mem_id)}",
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

    if mem_ids:
        connect("gen-ps", "P", mem_ids[-1], "P")
        for i in range(len(mem_ids) - 1, 0, -1):
            connect(mem_ids[i], "B", mem_ids[i - 1], "P")

    # ── 5. Linhas de pressão de grupo ────────────────────────────────────────
    #
    # Cada PressureLine recebe (n_cyls * _ANCHORS_PER_ACTUATOR) anchors,
    # numerados X1, X2, ..., Xn.
    # next_anchor(pl_id) entrega o próximo em ordem crescente — sem magic numbers.

    n_pl_anchors = n_cyls * _ANCHORS_PER_ACTUATOR
    all_anchors  = [f"X{i}" for i in range(1, n_pl_anchors + 1)]

    pl_grp_ids: list[str] = []
    _pl_counter: dict[str, int] = {}  # pl_id → próximo índice (começa em 1)

    for g in range(n_groups):
        pl_id = f"gen-pl-grp{g + 1}"
        pl_grp_ids.append(pl_id)
        _pl_counter[pl_id] = 1
        add_node(pl_id, "PressureLine", f"pressure_line_group:{g}",
                 properties={"anchors": all_anchors.copy()})

    def next_anchor(pl_id: str) -> str:
        """Retorna o próximo anchor livre da PressureLine, em ordem crescente."""
        idx = _pl_counter[pl_id]
        _pl_counter[pl_id] = idx + 1
        if idx > n_pl_anchors:
            raise RuntimeError(
                f"PressureLine {pl_id} esgotou todos os {n_pl_anchors} anchors. "
                f"Aumente _ANCHORS_PER_ACTUATOR (atual={_ANCHORS_PER_ACTUATOR})."
            )
        return f"X{idx}"

    # Conecta memórias / botão às pl-grp
    if mem_ids:
        for i, mem_id in enumerate(mem_ids):
            connect(mem_id, "A", pl_grp_ids[i], next_anchor(pl_grp_ids[i]))
        connect(mem_ids[0], "B", pl_grp_ids[-1], next_anchor(pl_grp_ids[-1]))
    else:
        # Circuito de 1 grupo: botão alimenta direto a pl-grp[0]
        connect("gen-btn", "A", pl_grp_ids[0], next_anchor(pl_grp_ids[0]))

    # ── 6. Válvulas de sinalização por evento ────────────────────────────────

    all_events_flat = [(g_idx, e_idx, letter, direction)
                       for g_idx, group in enumerate(groups)
                       for e_idx, (letter, direction) in enumerate(group)]

    for flat_idx, (g_idx, e_idx, letter, direction) in enumerate(all_events_flat):
        is_last_event = (e_idx == len(groups[g_idx]) - 1)
        is_last_group = (g_idx == n_groups - 1)
        s_id          = sig_id(letter, direction)
        sensor        = confirm_sensor(letter, direction)
        v42_pilot     = "PL" if direction == "+" else "PR"
        pl_current    = pl_grp_ids[g_idx]

        add_node(s_id, "Valve_3_2_Ways", f"signal_valve:{g_idx * 100 + e_idx}",
                 properties={
                     "actuators": {
                         "left":  {"type": "limit_switch", "sensor_name": sensor},
                         "right": {"type": "spring"},
                     }
                 })

        exh_sig = add_exhaust(f"exhaust:sig-{g_idx * 100 + e_idx}")
        connect(exh_sig, "R", s_id, "R")

        if is_last_event and not is_last_group:
            # ── Transição de grupo ───────────────────────────────────────────
            # sig.P ← barramento atual; sig.A → mc.PR (dispara troca de grupo)
            connect(pl_current, next_anchor(pl_current), s_id, "P")
            connect(s_id, "A", mem_ids[g_idx], "PR")

            # Pilot do PRIMEIRO evento do grupo seguinte via barramento seguinte
            next_letter, next_dir = all_events_flat[flat_idx + 1][2:4]
            next_pilot = "PL" if next_dir == "+" else "PR"
            pl_next = pl_grp_ids[g_idx + 1]
            connect(pl_next, next_anchor(pl_next), f"gen-v42-{next_letter}", next_pilot)

        elif is_last_event and is_last_group:
            # ── Fechamento do ciclo ──────────────────────────────────────────
            # sig.P ← barramento atual; sig.A → btn.P (fecha o ciclo)
            connect(pl_current, next_anchor(pl_current), s_id, "P")
            if mem_ids:
                connect(s_id, "A", "gen-btn", "P")

        else:
            # ── Evento normal ────────────────────────────────────────────────
            # sig.P ← barramento; sig.A → pilot do próximo v42
            connect(pl_current, next_anchor(pl_current), s_id, "P")
            next_letter, next_dir = all_events_flat[flat_idx + 1][2:4]
            next_pilot = "PL" if next_dir == "+" else "PR"
            connect(s_id, "A", f"gen-v42-{next_letter}", next_pilot)

            # Pilot do cilindro atual via barramento do grupo atual
            connect(pl_current, next_anchor(pl_current), f"gen-v42-{letter}", v42_pilot)

    # ── 7. Start: btn.A → mc[0].PL ──────────────────────────────────────────
    if mem_ids:
        connect("gen-btn", "A", mem_ids[0], "PL")

    return {
        "version":     1,
        "nodes":       nodes,
        "connections": connections,
    }