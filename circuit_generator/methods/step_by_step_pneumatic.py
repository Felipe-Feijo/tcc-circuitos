"""
Circuit generator for the step-by-step pneumatic method.

Topology generated for a sequence with M atoms (same atom concept used
in circuit_generator.methods.cascade: a single event, or a whole
"(...)" block of simultaneous moves):
  - 1 button_switch (Valve_3_2_Ways with button + spring)
  - Per cylinder: 1 double_acting_cylinder + 1 valve_4_2_ways (pilot+pilot)
                  + 1 dedicated PressureSource (port R) + 1 dedicated Exhaust (port P)
  - Per atom: 1 dedicated PressureLine + 1 bistable valve_3_2_ways memory
              (pilot+pilot) with a dedicated PressureSource (port P) and
              a dedicated Exhaust (port R)
  - Per event: 1 signaling valve_3_2_ways (limit_switch + spring)
               + 1 dedicated Exhaust (port R)
  - Serial confirmation (no AndValve) when an atom has 2+ events

Unlike cascade: no groups or A/B memory alternation -- each atom has its
own dedicated line and memory, never reused.
See docs/superpowers/specs/2026-07-10-step-by-step-pneumatic-design.md.

Main pressure flow (ring):
  MC_k.A -> gen-pl-step{k}
  gen-pl-step{k} -> MC_{k-1 mod M}.PR    (ring reset)
  btn.A -> MC_0.PL                       (atom 0's only SET source)
  confirmation(atom k-1) -> MC_k.PL      (SET for the other atoms)
  confirmation(atom M-1) -> btn.P        (cycle closure)

v42 pilots (via the atom's own line, no duplication):
  gen-pl-step{k} -> v42.PL/PR            (one tap per atom event)
"""

import uuid
from circuit_generator.sequence_parser import extract_cylinders


def _atomize(events: list[tuple]) -> list[list[tuple[int, str, str]]]:
    """Groups the whole sequence's events into atoms: consecutive events
    sharing the same parallel_id (3rd field) form one atom; the rest
    become single-event atoms. Each event is annotated with its
    original index in the sequence (flat_idx).

    Same logic as circuit_generator.sequence_parser._atomize and
    circuit_generator.methods.cascade._atomize_group, reimplemented here
    because step-by-step has no group layer -- it's a flat sequence of
    atoms, without the letter-repetition cut cascade uses to split
    groups.

    Accepts 2- or 3-field events, (letter, direction) or
    (letter, direction, parallel_id).
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

    # -- 1. Cylinders ---------------------------------------------------------

    for letter in cylinders:
        add_node(f"gen-cyl-{letter}", "DoubleActingCylinder", f"cylinder:{letter}",
                 properties={
                     "sensors": {
                         "retracted": {"enabled": True, "name": f"{letter.lower()}0"},
                         "extended":  {"enabled": True, "name": f"{letter.lower()}1"},
                     },
                     "default_state": "extended" if starts_extended[letter] else "retracted",
                 })

    # -- 2. 4/2 valves with dedicated PS and Exhaust -----------------------

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

    # -- 3. Start button --------------------------------------------------

    add_node("gen-btn", "Valve_3_2_Ways", "button",
             properties={
                 "actuators": {
                     "left":  {"type": "button", "mode": "latch"},
                     "right": {"type": "spring"},
                 }
             })
    connect(add_simple("Exhaust", "exhaust:btn-R"), "R", "gen-btn", "R")

    # -- 4. Pressure lines and memories per atom ---------------------------
    #
    #   Each atom (`_atomize`) gets its own dedicated PressureLine and its
    #   own bistable memory valve (Valve_3_2_Ways with two pneumatic
    #   pilots) -- never shared between atoms, unlike cascade. Ring
    #   reset: MC_k.PR comes from the NEXT atom's line (modulo M), so the
    #   last atom's reset comes from atom 0's line, closing the ring with
    #   no special case. Only the button sets MC_0 -- every other memory
    #   is set by the previous atom's confirmation (Task 4).

    atoms   = _atomize(events)
    n_atoms = len(atoms)

    pl_ids = [f"gen-pl-step{k}" for k in range(n_atoms)]
    mc_ids = [f"gen-mc-{k}" for k in range(n_atoms)]

    # The topology generator has no real screen position to decide how
    # far a PressureLine physically needs to reach -- only the layout
    # step (step_by_step_layout.py, via Grid.occupied_x_range) knows
    # that. Here, each PL starts empty and next_anchor() grows the list
    # on demand: exactly 1 anchor per real connection, never more, never
    # less, with no risk of running out.
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

    # Ring reset: MC_k.PR <- the next atom's line.
    for k in range(n_atoms):
        pr_source = pl_ids[(k + 1) % n_atoms]
        connect(pr_source, next_anchor(pr_source), mc_ids[k], "PR")

    # Atom 0's only SET source: the button.
    connect("gen-btn", "A", mc_ids[0], "PL")

    # -- 5. 4/2 pilots fed by the atom(s)' line(s) --------------------------
    #
    #   Each atom event drives its 4/2's matching pilot directly from the
    #   atom's line -- no duplication (a single tap per event), including
    #   when the atom is a "(...)" block with 2+ events: the line accepts
    #   as many taps as needed, so feeding 2+ pilots at once needs no
    #   extra valve (unlike cascade, which needs fan_out/AndValve just
    #   for this).
    #
    #   Multi-cycle (the same letter+direction repeated across
    #   non-adjacent atoms) makes 2+ independent lines target the SAME
    #   physical pilot -- without convergence this is physically invalid
    #   (two pressure sources on the same port). Collects in two passes
    #   (same algorithm cascade.py uses for the same problem, see
    #   docs/superpowers/specs/2026-07-10-cascade-multi-cycle-or-valve-design.md):
    #   pass 1 accumulates sources per pilot instead of connecting right
    #   away; pass 2 resolves -- 1 source connects directly (identical to
    #   the previous code, same call in the same order), 2+ sources
    #   become a binary OrValve chain (only has 2 inputs). Each OrValve's
    #   _role (f"or_valve:{letter}:{pilot}:{i}") is the contract
    #   step_by_step_layout.py reads to know how many columns to reserve
    #   on each side of the cylinder.

    triggers_for_pilot: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for k, atom in enumerate(atoms):
        pl_id = pl_ids[k]
        for e_idx, letter, direction in atom:
            key = (letter, direction)
            triggers_for_pilot.setdefault(key, []).append((pl_id, next_anchor(pl_id)))

    for (letter, direction), sources in triggers_for_pilot.items():
        v42_pilot = "PL" if direction == "+" else "PR"
        if len(sources) == 1:
            src_id, src_anchor = sources[0]
            connect(src_id, src_anchor, f"gen-v42-{letter}", v42_pilot)
            continue

        # X is the OrValve's LEFT input, Y the RIGHT one (anchor_local is
        # fixed, see or_valve.py) -- and step_by_step_layout.py positions
        # the chain growing LEFT of the cylinder on the PL side, but
        # RIGHT on the PR side (sign=-1/+1 in cyl_col +/- offset), with
        # the chain's previous OR (prev) always FARTHER from the
        # cylinder than the new one. On the PL side this already lines
        # up: prev sits to the left of each new OR, so prev->X (left) is
        # physically correct. On the PR side the direction flips: prev
        # sits to the RIGHT of each new OR (farther from the cylinder =
        # further right on that side) -- so prev must go to Y (right)
        # and the new source to X (left), otherwise the wire crosses
        # over/under the OR itself to reach the wrong side.
        prev_anchor_name, new_anchor_name = ("X", "Y") if v42_pilot == "PL" else ("Y", "X")

        prev_id, prev_anchor = sources[0]
        for i in range(1, len(sources)):
            or_id = add_simple("OrValve", f"or_valve:{letter}:{v42_pilot}:{i - 1}")
            connect(prev_id, prev_anchor, or_id, prev_anchor_name)
            src_id, src_anchor = sources[i]
            connect(src_id, src_anchor, or_id, new_anchor_name)
            prev_id, prev_anchor = or_id, "A"
        connect(prev_id, prev_anchor, f"gen-v42-{letter}", v42_pilot)

    # -- 6. Confirmation per atom --------------------------------------------
    #
    #   Each atom produces a single confirmation (never duplicated --
    #   unlike cascade, there's no fan_out here: the sequence is flat, so
    #   every atom has exactly one "next"). A lone event uses a single
    #   signaling valve; an N>1-event block uses N valves chained in
    #   series -- the 1st pulls P from the atom's line, the rest pull P
    #   from the previous sig (logical AND without an AndValve). Atom k's
    #   confirmation sets MC_{k+1}.PL; the last atom's confirmation
    #   closes the cycle by feeding btn.P (never MC_0.PL directly).

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
