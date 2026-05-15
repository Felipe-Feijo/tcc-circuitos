"""
Gerador de circuito pelo método cascata (pneumático).

Topologia gerada para N grupos:
  - 1 pressure_source
  - 1 pressure_line principal
  - 1 button_switch
  - (N-1) válvulas de memória valve_5_2_ways encadeadas
  - N pressure_lines de grupo
  - Por cilindro: 1 double_acting_cylinder + 1 valve_4_2_ways (pilot+pilot)
  - Por evento: 1 valve_3_2_ways de sinalização (limit_switch + spring)
  - Exhausts nas saídas R1, R2 de cada memória
"""

from circuit_generator.sequence_parser import extract_cylinders, split_into_groups


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

    # ── 1. Cilindros (devem vir ANTES das válvulas para registrar sensores) ──

    for letter in cylinders:
        add_node(f"gen-cyl-{letter}", "DoubleActingCylinder", f"cylinder:{letter}",
                 properties={
                     "sensors": {
                         "retracted": {"type": "reed", "name": sensor_ret(letter)},
                         "extended":  {"type": "reed", "name": sensor_ext(letter)},
                     }
                 })

    # ── 2. Válvulas 4/2 (pilot + pilot, biestável) ───────────────────────────

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

    # ── 3. Infraestrutura ────────────────────────────────────────────────────

    # anchors: X1=ps, X2=btn, X3..=v42 (1 por cil), Xn=mem topo (se >1 grupo)
    n_main_anchors = 2 + len(cylinders) + (1 if n_groups > 1 else 0)
    main_anchors   = [f"X{i}" for i in range(1, n_main_anchors + 1)]

    add_node("gen-ps",      "PressureSource", "pressure_source")
    add_node("gen-pl-main", "PressureLine",   "pressure_line_main",
             properties={"anchors": main_anchors})
    add_node("gen-btn", "Valve_3_2_Ways", "button",
             properties={
                 "actuators": {
                     "left":  {"type": "button"},
                     "right": {"type": "spring"},
                 }
             })

    connect("gen-ps",      "P",  "gen-pl-main", "X1")
    connect("gen-pl-main", "X2", "gen-btn", "P")

    for i, letter in enumerate(cylinders):
        connect("gen-pl-main", f"X{3 + i}", f"gen-v42-{letter}", "P")

    # ── 4. Memórias (valve_5_2_ways) ─────────────────────────────────────────
    #
    # Encadeamento de pressão (da última para a primeira):
    #   pl_main → mem[-1].P
    #   mem[i].B → mem[i-1].P   (i > 0)
    #   mem[0].B → pl_grp[-1]   (último grupo = repouso/retorno)
    #   mem[i].A → pl_grp[i]

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
        connect("gen-pl-main", f"X{2 + len(cylinders) + 1}", mem_ids[-1], "P")
        for i in range(len(mem_ids) - 1, 0, -1):
            connect(mem_ids[i], "B", mem_ids[i - 1], "P")

    # ── 5. Linhas de pressão de grupo ────────────────────────────────────────

    pl_grp_ids = []
    for g in range(n_groups):
        pl_id    = f"gen-pl-grp{g + 1}"
        n_events = len(groups[g])
        anchors  = [f"X{i}" for i in range(1, n_events + 2)]  # X1=entrada + 1 por evento
        pl_grp_ids.append(pl_id)
        add_node(pl_id, "PressureLine", f"pressure_line_group:{g}",
                 properties={"anchors": anchors})

    if mem_ids:
        for i, mem_id in enumerate(mem_ids):
            connect(mem_id, "A", pl_grp_ids[i], "X1")
        connect(mem_ids[0], "B", pl_grp_ids[-1], "X1")
    else:
        # 1 único grupo: button.A → pl_grp direto
        connect("gen-btn", "A", pl_grp_ids[0], "X1")

    # ── 6. Válvulas de sinalização por evento ────────────────────────────────
    #
    # Regras:
    #   - Sempre: pl_grp.Xi → sig.P  e  sig.A → v42.PL/PR (aciona cilindro)
    #   - Último evento de grupo não-final: sig.A → mem[g].PR  (transição)
    #   - Último evento do ciclo: sig.A → mem[0].PL (fechamento, em série com btn)
    #
    # Start: btn.A → mem[0].PL — o botão libera pressão da pl_main para a mem.
    # O último sig do ciclo também vai a mem[0].PL; ambos precisam estar ativos
    # ao mesmo tempo (AND em série pela própria topologia da linha de pressão).

    for g_idx, group in enumerate(groups):
        is_last_group = (g_idx == n_groups - 1)

        for e_idx, (letter, direction) in enumerate(group):
            is_last_event = (e_idx == len(group) - 1)
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

            # pressão do grupo → P da válvula de sinalização
            connect(pl_grp_ids[g_idx], f"X{e_idx + 2}", s_id, "P")

            # sempre aciona o cilindro correspondente
            connect(s_id, "A", f"gen-v42-{letter}", v42_pilot)

            if is_last_event and not is_last_group:
                # transição de grupo: sig.A → PR da memória
                connect(s_id, "A", mem_ids[g_idx], "PR")
            elif is_last_event and is_last_group and mem_ids:
                # fechamento do ciclo: último sig → mem[0].PL
                # (o botão também precisa estar pressionado — AND em série)
                connect(s_id, "A", mem_ids[0], "PL")

    # ── 7. Start: btn.A → mem[0].PL ─────────────────────────────────────────
    # O botão em série com o último sensor forma o AND de start.
    # A topologia é: pl_main → btn.P → btn.A → mem[0].PL
    # E também:      last_sig.A → mem[0].PL  (ambas as condições devem ser true)
    if mem_ids:
        connect("gen-btn", "A", mem_ids[0], "PL")


    return {
        "version":     1,
        "nodes":       nodes,
        "connections": connections,
    }