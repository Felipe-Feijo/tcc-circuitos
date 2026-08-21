"""
Circuit generator for the step-by-step electric method.

Topology generated for a sequence with M atoms (same atom concept used
in circuit_generator.methods.step_by_step_pneumatic: a single event, or
a whole "(...)" block of simultaneous moves):
  - 1 VoltageSource + 1 Ground (electric buses, anchors grow on demand,
    same pattern as the pneumatic PressureLine)
  - 1 cycle-bootstrap ButtonSwitch
  - Per cylinder: 1 DoubleActingCylinder + 1 Valve_4_2_Ways (P/R with
    dedicated PressureSource/Exhaust, same as pneumatic)
  - Per atom: 1 RelayCoil K_k + 3 step RelaySwitches (ramo A: previous
    atom's end-of-stroke sensor(s) in series + the previous atom's K
    contact; ramo B: K_k's own self-hold; reset: NC of the next atom's
    K) -- logic ring, see docs/superpowers/specs/
    2026-07-31-step-by-step-electric-power-contacts-design.md
  - Per (cylinder, direction) present in the sequence: 1 SolenoidCoil Y
    (sensor "Y{letter}{1|0}") + 1 dedicated NO power contact per atom
    that triggers that move (relay_sensor = the atom's K), all in
    parallel feeding the same Y coil -- multi-cycle becomes just one
    more parallel contact, no sig or OrValve.
  - 4/2 piloting: always the "solenoid" actuator, reading the matching
    (cylinder, direction)'s Y directly.

Logic ring (self-maintaining, self-holding):
  VoltageSource --> [atom k-1's end-of-stroke sensor(s)] --> [K_{k-1} NO] --\
  VoltageSource --> [K_k NO self-hold] -------------------------------------+--> [K_{k+1} NC] --> K_k --> Ground
  (atom M-1 only) VoltageSource --> [button NO] -----------------------/
  (atom 0 only) VoltageSource --> [K_last NO] --> [start button NO] --/

Power zone (independent per (cylinder, direction)):
  VoltageSource --> [K_k1 NO] --\
  VoltageSource --> [K_k2 NO] ----+--> Y_{letter}{dir} --> Ground   (k1, k2, ... = atoms triggering that move)

Unlike pneumatic: there's no PressureLine or 3/2 memory -- the "active
step" is remembered by the K_k's own energized/de-energized state.
"""

import uuid
from circuit_generator.sequence_parser import extract_cylinders


def _atomize(events: list[tuple]) -> list[list[tuple[int, str, str]]]:
    """Groups the whole sequence's events into atoms: consecutive events
    sharing the same parallel_id (3rd field) form one atom; the rest
    become single-event atoms. Each event is annotated with its
    original index in the sequence (flat_idx).

    Reimplemented here (not shared with step_by_step_pneumatic._atomize)
    -- same principle followed throughout the rest of the generator for
    this utility function.
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
            f"step_by_step_electric requires at least 3 atoms in the relay ring "
            f"(sequence generated {n_atoms})."
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

    # Initial state: if the first move is "-", the cylinder starts extended.
    first_event     = {letter: direction for letter, direction, *_ in reversed(events)}
    starts_extended = {letter: first_event[letter] == "-" for letter in cylinders}

    # -- 1. Cylinders (identical to pneumatic) -----------------------------------

    for letter in cylinders:
        add_node(f"gen-cyl-{letter}", "DoubleActingCylinder", f"cylinder:{letter}",
                 properties={
                     "sensors": {
                         "retracted": {"type": "reed", "name": f"{letter.lower()}0"},
                         "extended":  {"type": "reed", "name": f"{letter.lower()}1"},
                     },
                     "default_state": "extended" if starts_extended[letter] else "retracted",
                 })

    # -- 2. 4/2 valves with dedicated PS and Exhaust (actuators stay empty
    #      here -- filled in section 6, "power zone") ----------------------

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

    # -- 3. Electric buses (source, ground) and bootstrap button ------------

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

    # -- 4. K_k coil ring (one per atom) and self-holding steps -------------
    #
    #   Each atom gets exactly 1 RelayCoil (K_k, sensor "K{k+1}",
    #   1-indexed) and a step of 3 RelaySwitch contact groups:
    #     - ramo A (start): serial chain of NO contacts reading the
    #       PREVIOUS atom's end-of-stroke sensors (1 contact per atom
    #       event, in series -- same serial-confirmation technique
    #       already used in pneumatic), followed by 1 NO contact of the
    #       previous atom's K.
    #     - ramo B (self-hold): 1 NO contact of K_k itself, in parallel
    #       with ramo A.
    #     - reset: 1 NC contact of the NEXT atom's K (modulo M -- closes
    #       the ring with no special case), after the point where ramo A
    #       and ramo B converge.
    #   Atom M-1 (the cycle's last one) gets a third parallel branch,
    #   with only the bootstrap ButtonSwitch.
    #
    #   K_k is a LOGIC-only relay -- it doesn't drive anything pneumatic
    #   directly. The power coil (Y, section 6) is a separate physical
    #   component, driven by one of K_k's dedicated NO contacts.

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

        # Ramo A: serial chain of sensor contacts + the previous K's contact.
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

        # Ramo B: K_k's own self-hold.
        ramo_b_contact = contact(f"{k}-ramo_b_self", "NO", f"K{k + 1}")

        # The source feeds the start of each branch (2 parallel taps).
        connect("gen-vsource", next_bus_anchor("gen-vsource"), first_sensor_contact, "T")
        connect("gen-vsource", next_bus_anchor("gen-vsource"), ramo_b_contact, "T")

        # Both branches converge on the reset contact (NC of the next K).
        reset_contact = contact(f"{k}-reset_nc", "NC", f"K{next_k + 1}")

        # Cycle-start button: FIRST atom only, in series at the end of
        # ramo A (after the previous K's contact, before converging with
        # ramo B) -- K0 only energizes if the sensor(s) + last K + this
        # button are all closed, giving exact manual control over when
        # the cycle starts (instead of K0 firing on its own as soon as
        # sensor+K are automatically satisfied).
        if k == 0:
            connect(ramo_a_prev_contact, "B", "gen-btn-start", "T")
            connect("gen-btn-start", "B", reset_contact, "T")
        else:
            connect(ramo_a_prev_contact, "B", reset_contact, "T")
        connect(ramo_b_contact, "B", reset_contact, "T")

        # Bootstrap: only the cycle's last atom gets the button branch.
        if k == n_atoms - 1:
            connect("gen-vsource", next_bus_anchor("gen-vsource"), "gen-btn", "T")
            connect("gen-btn", "B", reset_contact, "T")

        connect(reset_contact, "B", k_ids[k], "T")
        connect(k_ids[k], "B", "gen-ground", next_bus_anchor("gen-ground"))

    # -- 5. Grouping by (cylinder, direction): which atoms trigger each
    #      move -- same map used by pneumatic/cascade for multi-cycle,
    #      here it becomes each Y coil's list of parallel power contacts --

    triggers_for_pilot: dict[tuple[str, str], list[int]] = {}
    for k, atom in enumerate(atoms):
        for e_idx, letter, direction in atom:
            triggers_for_pilot.setdefault((letter, direction), []).append(k)

    # -- 6. Power zone: 1 Y coil per (cylinder, direction) + 1 dedicated
    #      NO power contact per atom that triggers that move, all in
    #      parallel feeding the same coil ------------------------------------
    #
    #   Multi-cycle (2+ atoms triggering the same (letter, direction))
    #   becomes just one more parallel contact, with no dedicated
    #   convergence component -- the electric bus already supports
    #   multiple connections on the same anchor (AnchorItem.connections
    #   is a list, not a single slot). The 4/2 always pilots via the
    #   "solenoid" actuator reading the matching Y -- no single-case vs.
    #   multi-cycle branching.

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
