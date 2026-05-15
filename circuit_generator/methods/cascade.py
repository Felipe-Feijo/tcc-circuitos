"""
Gerador de circuito pelo método cascata (pneumático).

Topologia gerada para N grupos:
  - 1 pressure_source principal (alimenta memória e botão)
  - 1 button_switch (Valve_3_2_Ways com button + spring)
  - (N-1) válvulas de memória valve_5_2_ways encadeadas
  - N pressure_lines de grupo (barramentos com anchors generosos)
  - Por cilindro: 1 double_acting_cylinder + 1 valve_4_2_ways (pilot+pilot)
                  + 1 PressureSource dedicado (porta R) + 1 Exhaust dedicado (porta P)
  - Por evento: 1 valve_3_2_ways de sinalização (limit_switch + spring)
                + 1 Exhaust dedicado (porta R)
  - Exhausts nas saídas R1, R2 de cada memória
  - 1 Exhaust dedicado na porta R do botão

Fluxo de pressão principal:
  gen-ps → mc[-1].P  (pressão da fonte vai direto à última memória)
  mc.A → pl_grp[i]   (cada memória alimenta sua pl de grupo)
  mc[0].B → pl_grp[-1]  (grupo de retorno/repouso)

Sinalização:
  pl_grp.Xi → sig.P  (grupo alimenta sig)
  sig.A → v42.PL/PR  (sinalização aciona cilindro via pl-grp)
  sig_transição.A → mc[g].PR  (transição de grupo: sig aciona memória)
  sig_fechamento.A → btn.P    (último sinal do ciclo alimenta o botão — AND série)
  btn.A → mc[0].PL            (botão aciona memória de start)

  Para transição de grupo (sinal entre grupos):
  mc[g].PR → sig_transição.A  (a memória commutada alimenta a sig — lógica AND)

v42 pilots:
  pl_grp[g_ext].Xn → v42.PL   (extensão: via barramento do grupo onde A+ está)
  pl_grp[g_ret].Xn → v42.PR   (retração: via barramento do grupo onde A- está)
"""

import uuid
from circuit_generator.sequence_parser import extract_cylinders, split_into_groups

# Número de anchors reservados em cada PressureLine de grupo.
# Valor generoso para dar espaço de roteamento no canvas.
_PL_GRP_ANCHORS = 21


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

    def add_exhaust(role="exhaust"):
        """Cria um Exhaust com UUID e retorna seu id."""
        uid = str(uuid.uuid4())
        add_node(uid, "Exhaust", role)
        return uid

    def add_ps(role="pressure_source"):
        """Cria um PressureSource com UUID e retorna seu id."""
        uid = str(uuid.uuid4())
        add_node(uid, "PressureSource", role)
        return uid

    def connect(src_node, src_anchor, tgt_node, tgt_anchor):
        connections.append({
            "source": {"node": src_node, "anchor": src_anchor},
            "target": {"node": tgt_node, "anchor": tgt_anchor},
        })

    def next_pl_anchor(pl_id):
        """Retorna o próximo anchor livre da PressureLine de grupo."""
        idx = _pl_grp_anchor_counter.get(pl_id, 4)
        _pl_grp_anchor_counter[pl_id] = idx + 1
        return f"X{idx}"

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
    # Cada v42 tem:
    #   - porta P conectada a um Exhaust dedicado  (drena quando não aciona)
    #   - porta R conectada a um PressureSource dedicado  (retorno de pressão)
    # Os pilots (PL/PR) serão conectados mais tarde via pl-grp.

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

        # P → Exhaust dedicado, R → PressureSource dedicado
        exh_v42 = add_exhaust(f"exhaust:v42-{letter}-P")
        ps_v42  = add_ps(f"pressure_source:v42-{letter}-R")
        connect(exh_v42, "R", f"gen-v42-{letter}", "P")
        connect(ps_v42,  "P", f"gen-v42-{letter}", "R")

    # ── 3. Infraestrutura principal ──────────────────────────────────────────
    # gen-ps → mc[-1].P  (sem pl-main)
    # btn.P vem do último sinal do ciclo (ligado mais adiante)
    # btn.R → Exhaust dedicado

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

    # gen-ps → mc[-1].P
    if mem_ids:
        connect("gen-ps", "P", mem_ids[-1], "P")
        for i in range(len(mem_ids) - 1, 0, -1):
            connect(mem_ids[i], "B", mem_ids[i - 1], "P")

    # ── 5. Linhas de pressão de grupo ────────────────────────────────────────
    # Anchors generosos (_PL_GRP_ANCHORS total).
    #
    # Estrutura de anchors do gabarito:
    #   mc.A → X9  (grupo par: A)  |  mc.B → X8  (grupo ímpar: B)
    #   Chain: X18→X17→...→X9→X8→...→X4→X1  (X4→X1 direto, sem X2/X3)
    #          X1→X2→X3→X19→X20→X21          (cauda)
    #   sig.P do evento 0 do grupo 1: X7    | grupo 2: X19 (cauda)
    #   sig.P do último (transição/fechamento): X1 do próximo | X18
    #   pilot v42: X17 (grupo 1), X12 (grupo 2)

    # Anchor de entrada da mc: alterna por grupo (A=X9, B=X8, ...)
    def mc_entry_anchor(g_idx):
        return f"X{9 - g_idx}"  # g0→X9, g1→X8, g2→X7, ...

    _pl_sig_anchor_counter   = {}  # para sig.P (X18 descendo)
    _pl_pilot_anchor_counter = {}  # para v42 pilots (X17 descendo)

    all_anchors = [f"X{i}" for i in range(1, _PL_GRP_ANCHORS + 1)]

    pl_grp_ids = []
    for g in range(n_groups):
        pl_id = f"gen-pl-grp{g + 1}"
        pl_grp_ids.append(pl_id)
        _pl_sig_anchor_counter[pl_id]   = 18
        _pl_pilot_anchor_counter[pl_id] = 17
        add_node(pl_id, "PressureLine", f"pressure_line_group:{g}",
                 properties={"anchors": all_anchors.copy()})

    def next_pl_sig_anchor(pl_id):
        idx = _pl_sig_anchor_counter[pl_id]
        _pl_sig_anchor_counter[pl_id] = idx - 1
        return f"X{idx}"

    def next_pl_pilot_anchor(pl_id):
        idx = _pl_pilot_anchor_counter[pl_id]
        _pl_pilot_anchor_counter[pl_id] = idx - 1
        return f"X{idx}"

    # Conecta memórias às pl-grp com anchor alternado por grupo
    if mem_ids:
        for i, mem_id in enumerate(mem_ids):
            connect(mem_id, "A", pl_grp_ids[i], mc_entry_anchor(i))
        connect(mem_ids[0], "B", pl_grp_ids[-1], mc_entry_anchor(len(pl_grp_ids) - 1))
    else:
        connect("gen-btn", "A", pl_grp_ids[0], mc_entry_anchor(0))

    # Chain interna das pl-grp igual ao gabarito:
    # X18→...→X9→X8→...→X4→X1 (X4→X1 direto) → X2→X3→X19→X20→X21
    def add_pl_grp_chain(pl_id):
        def ch(a, b):
            connect(pl_id, f"X{a}", pl_id, f"X{b}")
        for i in range(18, 4, -1): ch(i, i - 1)  # X18→X4
        ch(4, 1)                                   # X4→X1  (direto, pula X2/X3)
        ch(1, 2); ch(2, 3); ch(3, 19); ch(19, 20); ch(20, 21)

    for pl_id in pl_grp_ids:
        add_pl_grp_chain(pl_id)

    # ── 6. Válvulas de sinalização por evento ────────────────────────────────
    #
    # Anchors por papel (derivados do gabarito):
    #
    # sig.P de evento normal (não-último):
    #   grupo 0: ala esquerda, descendo de X8  (X8, X7, X6, ...)
    #   grupo 1: cauda, crescendo de X19       (X19, X20, X21)
    #
    # sig.P de transição (último do grupo não-final):
    #   ancora em X1 do grupo ATUAL (não do próximo)
    #
    # sig.P de fechamento (último do ciclo):
    #   ala direita de X18 descendo (X18, ...)
    #
    # pilot v42 via barramento:
    #   grupo 0: X17 descendo  (X17, X16, ...)
    #   grupo 1: X12 descendo  (X12, X11, ...)
    #
    # sig.A de evento normal → v42 do PRÓXIMO evento (cascata real)
    # sig.A de transição     → nenhum v42 direto (apenas mc.PR→sig)
    # sig.A de fechamento    → btn.P

    # Contadores de sig.P por grupo
    # Grupo par  (0,2,...): barramento → sig.P, ala esquerda desc de X7
    # Grupo ímpar (1,3,...): sig.P → barramento, cauda cresc de X19
    # Fechamento: barramento → sig.P, ala direita desc de X18
    _pl_sig_left_counter  = {pl: 7  for pl in pl_grp_ids}   # grupos pares: X7 desc
    _pl_sig_tail_counter  = {pl: 19 for pl in pl_grp_ids}   # grupos ímpares: X19 cresc
    _pl_sig_right_counter = {pl: 18 for pl in pl_grp_ids}   # fechamento: X18 desc

    # Contadores de pilot por grupo: grupo 0 → X17, grupo 1 → X12, ...
    _pl_pilot_by_grp = []
    for g in range(n_groups):
        start = 17 - g * 5
        _pl_pilot_by_grp.append({"pl": pl_grp_ids[g], "next": start})

    def next_sig_p_anchor(g_idx, role):
        pl_id = pl_grp_ids[g_idx]
        if role == "normal":
            if g_idx % 2 == 0:
                idx = _pl_sig_left_counter[pl_id]
                _pl_sig_left_counter[pl_id] -= 1
            else:
                idx = _pl_sig_tail_counter[pl_id]
                _pl_sig_tail_counter[pl_id] += 1
        else:
            idx = _pl_sig_right_counter[pl_id]
            _pl_sig_right_counter[pl_id] -= 1
        return f"X{idx}"

    def connect_sig_p(g_idx, pl_anchor, s_id):
        """Conecta sig.P → pl-grp (direção uniforme, simulador é não-direcional)."""
        connect(s_id, "P", pl_grp_ids[g_idx], pl_anchor)

    def next_pilot_anchor(g_idx):
        info = _pl_pilot_by_grp[g_idx]
        idx = info["next"]
        info["next"] -= 1
        return pl_grp_ids[g_idx], f"X{idx}"

    all_events_flat = [(g_idx, e_idx, letter, direction)
                       for g_idx, group in enumerate(groups)
                       for e_idx, (letter, direction) in enumerate(group)]

    for flat_idx, (g_idx, e_idx, letter, direction) in enumerate(all_events_flat):
        is_last_event = (e_idx == len(groups[g_idx]) - 1)
        is_last_group = (g_idx == n_groups - 1)
        s_id          = sig_id(letter, direction)
        sensor        = confirm_sensor(letter, direction)
        v42_pilot     = "PL" if direction == "+" else "PR"

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
            # Transição: sig.P → pl_grp[g].X1 (sig alimenta o barramento), mc.PR → sig.A
            connect(s_id, "P", pl_grp_ids[g_idx], "X1")
            connect(mem_ids[g_idx], "PR", s_id, "A")
            # Pilot: aciona o próximo cilindro via barramento do PRÓXIMO grupo
            next_letter, next_dir = all_events_flat[flat_idx + 1][2:4]
            next_pilot = "PL" if next_dir == "+" else "PR"
            next_g_idx = g_idx + 1
            pl_id, pa = next_pilot_anchor(next_g_idx)
            connect(pl_id, pa, f"gen-v42-{next_letter}", next_pilot)

        elif is_last_event and is_last_group:
            # Fechamento: barramento → sig.P (ala direita), sig.A → btn.P
            sig_p_anch = next_sig_p_anchor(g_idx, "close")
            connect(pl_grp_ids[g_idx], sig_p_anch, s_id, "P")
            if mem_ids:
                connect(s_id, "A", "gen-btn", "P")

        else:
            # Normal: sig.P ↔ barramento (direção depende do grupo), sig.A → próximo v42
            sig_p_anch = next_sig_p_anchor(g_idx, "normal")
            connect_sig_p(g_idx, sig_p_anch, s_id)
            next_letter, next_dir = all_events_flat[flat_idx + 1][2:4]
            next_pilot = "PL" if next_dir == "+" else "PR"
            connect(s_id, "A", f"gen-v42-{next_letter}", next_pilot)
            # Pilot via barramento: aciona cilindro atual
            pl_id, pa = next_pilot_anchor(g_idx)
            connect(pl_id, pa, f"gen-v42-{letter}", v42_pilot)

    # ── 7. Start: btn.A → mc[0].PL ──────────────────────────────────────────
    if mem_ids:
        connect("gen-btn", "A", mem_ids[0], "PL")

    return {
        "version":     1,
        "nodes":       nodes,
        "connections": connections,
    }