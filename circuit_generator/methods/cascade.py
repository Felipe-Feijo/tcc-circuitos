"""
Circuit generator for the cascade (pneumatic) method.

Topology generated for N groups:
  - 1 main pressure_source (feeds the memory and the button)
  - 1 button_switch (Valve_3_2_Ways with button + spring)
  - (N-1) chained valve_5_2_ways memory valves
  - N group pressure_lines (buses with per-actuator anchors)
  - Per cylinder: 1 double_acting_cylinder + 1 valve_4_2_ways (pilot+pilot)
                  + 1 dedicated PressureSource (port R) + 1 dedicated Exhaust (port P)
  - Per event: 1 signaling valve_3_2_ways (limit_switch + spring)
               + 1 dedicated Exhaust (port R)
  - Exhausts on each memory's R1, R2 outputs
  - 1 dedicated Exhaust on the button's R port

Group pressure lines:
  Each PressureLine gets (n_cyls * _ANCHORS_PER_ACTUATOR) anchors,
  numbered X1, X2, X3, ... with no "wing" or "tail" logic.
  A simple counter per pl_id hands out the next free anchor in ascending order.

Main pressure flow:
  gen-ps -> mc[-1].P  (the source's pressure goes straight to the last memory)
  mc.A -> pl_grp[i]   (each memory feeds its group's pl)
  mc[0].B -> pl_grp[-1]  (return/rest group)

Signaling:
  pl_grp.Xi -> sig.P  (group feeds sig -- anchor consumed in order)
  sig.A -> v42.PL/PR  (signaling triggers the cylinder)
  transition_sig.A -> mc[g].PR  (group transition)
  closure_sig.A -> btn.P    (cycle's last signal -> serial AND with the button)
  btn.A -> mc[0].PL          (button triggers the start memory)

v42 pilots (via bus):
  pl_grp[g_ext].Xi -> v42.PL   (extension: the bus of the group where A+ is)
  pl_grp[g_ret].Xi -> v42.PR   (retraction: the bus of the group where A- is)
"""

import uuid
from collections import Counter
from circuit_generator.sequence_parser import extract_cylinders, split_into_groups

# Anchors reserved per event (occurrence in the sequence) per cylinder.
# 20 guarantees slack for sig.P, pilots and the memory entry.
_ANCHORS_PER_EVENT = 20


def _atomize_group(group: list[tuple]) -> list[list[tuple[int, str, str]]]:
    """
    Groups a cascade group's events into atoms: a lone event becomes a
    size-1 atom; consecutive events sharing the same parallel_id
    (simultaneous block) become a single atom. Each event is annotated
    with its original e_idx within the group (needed to name signaling
    valves' _role, which uses g_idx*100+e_idx).

    Mirrors sequence_parser._atomize (same parallel_id grouping logic),
    but also returns e_idx -- which sequence_parser doesn't expose since
    it doesn't need it to decide group cuts.

    Accepts 2- or 3-field events, (letter, direction) or
    (letter, direction, parallel_id) -- same tolerance used throughout
    this module since sub-project 1.
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

    # Initial state: if the first move is "-", the cylinder starts extended.
    first_event     = {letter: direction for letter, direction, *_ in reversed(events)}
    starts_extended = {letter: first_event[letter] == "-" for letter in cylinders}

    # -- 1. Cylinders ------------------------------------------------------------

    for letter in cylinders:
        add_node(f"gen-cyl-{letter}", "DoubleActingCylinder", f"cylinder:{letter}",
                 properties={
                     "sensors": {
                         "retracted": {"type": "reed", "name": f"{letter.lower()}0"},
                         "extended":  {"type": "reed", "name": f"{letter.lower()}1"},
                     },
                     "default_state": "extended" if starts_extended[letter] else "retracted",
                 })

    # -- 2. 4/2 valves with dedicated PS and Exhaust -----------------------------

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

    # -- 3. Start button ----------------------------------------------------------

    add_node("gen-btn", "Valve_3_2_Ways", "button",
             properties={
                 "actuators": {
                     "left":  {"type": "button"},
                     "right": {"type": "spring"},
                 }
             })
    connect(add_simple("Exhaust", "exhaust:btn-R"), "R", "gen-btn", "R")

    # -- 4. Memories (valve_5_2_ways) --------------------------------------------
    # mem_ids[i] = mc[i]; mc[0] receives btn, mc[N-2] is the topmost.

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

    # -- 5. Group pressure lines --------------------------------------------------

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
                f"PressureLine {pl_id} ran out of all {n_pl_anchors} anchors. "
                f"Increase _ANCHORS_PER_EVENT (current={_ANCHORS_PER_EVENT})."
            )
        return f"X{idx}"

    # -- 5b. Pressure chaining -----------------------------------------------------
    #
    #   btn.A    -> mc[0].P
    #   mc[i].A  -> mc[i+1].P         for i = 0..N-3
    #   mc[N-2].A -> pl[0]            (topmost feeds the first pl)
    #   mc[i].B  -> pl[N-1-i]         mc[0].B->pl[N-1], mc[1].B->pl[N-2], ...

    if mem_ids:
        connect(add_simple("PressureSource", "pressure_source:mc0"), "P", mem_ids[0], "P")
        for i in range(n_mc - 1):
            connect(mem_ids[i], "A", mem_ids[i + 1], "P")
        connect(mem_ids[-1], "A", pl_grp_ids[0], next_anchor(pl_grp_ids[0]))
        for i, mem_id in enumerate(mem_ids):
            pl_idx = n_groups - 1 - i
            connect(mem_id, "B", pl_grp_ids[pl_idx], next_anchor(pl_grp_ids[pl_idx]))
    else:
        # 1 group: btn feeds pl[0] directly
        connect("gen-btn", "A", pl_grp_ids[0], next_anchor(pl_grp_ids[0]))

    # -- 6. Trigger and confirmation per atom --------------------------------------
    #
    #   Each cascade group is split into "atoms" (_atomize_group): a lone
    #   event, or a whole "(...)" block (events sharing a parallel_id).
    #   An atom fires each of its events exactly once (one dedicated
    #   source per event -- never duplicated) and produces `fan_out`
    #   independent confirmation sets: one per event of the NEXT atom, or
    #   1 if it's the group's last atom (feeds mc.PR/btn.P). Each
    #   confirmation set is a dedicated group of signaling valves (same
    #   sensor, same bus P), chained in series if the atom has more than
    #   one event -- the 1st sig pulls P from the bus, the rest pull P
    #   from the previous sig's output (A) (logical AND with no AndValve;
    #   see spec docs/superpowers/specs/
    #   2026-07-11-serial-confirmation-no-andvalve-design.md).
    #
    #   fan_out is always a LOCAL lookup at just the next atom -- it never
    #   accumulates across multiple atoms (only the trigger of the atom
    #   immediately before a block needs duplicating; the rest of the
    #   serial chain before it keeps a single set).
    #
    #   With no "(...)" blocks, every atom has size 1 and fan_out=1
    #   everywhere -- the algorithm collapses exactly to the
    #   event-by-event wiring from before this sub-project.
    #
    #   Multi-cycle (sub-project 2): when the same 4/2 pilot receives more
    #   than one trigger source, the sources are accumulated in
    #   `triggers_for_pilot` and resolved in pass 2 (below, unchanged) --
    #   1 source connects directly; 2+ sources converge via OrValve.

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

        entry_sources: list[tuple[str, str]] | None = None  # 1:1 with the current atom's events

        for atom_idx, atom in enumerate(atoms):
            is_last_atom = (atom_idx == n_atoms - 1)
            fan_out      = 1 if is_last_atom else len(atoms[atom_idx + 1])

            if entry_sources is None:
                entry_sources = [(pl_current, next_anchor(pl_current)) for _ in atom]

            # Fires each of the atom's events exactly once.
            for slot_idx, (e_idx, letter, direction) in enumerate(atom):
                v42_pilot = "PL" if direction == "+" else "PR"
                triggers_for_pilot.setdefault((letter, v42_pilot), []).append(
                    entry_sources[slot_idx])

            # Produces `fan_out` independent confirmation sets.
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

    # -- 6b. Resolves the trigger sources accumulated per pilot --------------------
    #
    #   1 source  -> connects directly to the pilot, in the same connect()
    #               call order used before this sub-project (preserves
    #               the exact topology for 1-cycle-per-cylinder sequences).
    #   2+ sources -> binary OrValve chain: each OR's output feeds the
    #               next one's free input, until the last OR feeds the
    #               4/2's pilot.

    for (letter, pilot_side), sources in triggers_for_pilot.items():
        if len(sources) == 1:
            src_id, src_anchor = sources[0]
            if src_anchor == "A":
                # chained source (sig.A) -> the 4/2's pilot
                connect(src_id, src_anchor, f"gen-v42-{letter}", pilot_side)
            else:
                # direct source from the bus -> the 4/2's pilot (the 4/2
                # is the call's "source", the bus is the "target" -- same
                # order used before this sub-project)
                connect(f"gen-v42-{letter}", pilot_side, src_id, src_anchor)
        else:
            current = sources[0]
            for i, nxt in enumerate(sources[1:]):
                or_id = add_simple("OrValve", f"or_valve:{letter}:{pilot_side}:{i}")
                connect(current[0], current[1], or_id, "X")
                connect(nxt[0], nxt[1], or_id, "Y")
                current = (or_id, "A")
            connect(current[0], current[1], f"gen-v42-{letter}", pilot_side)

    # -- 7. Memory PL pilots via PressureLines --------------------------------------
    #
    #   mc[0].PL <- btn.A
    #   mc[i].PL <- pl[n_mc-i+1]  for i > 0

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