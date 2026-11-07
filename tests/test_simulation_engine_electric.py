import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.simulation_engine import SimulationEngine
from simulation.nodes.nodes import Node
from simulation.connections import Connection


def _terminal(node_id, anchor_type=None):
    """Nó de teste com uma única anchor elétrica, opcionalmente 'source'/'ground'."""
    node = Node(node_id, "test_terminal", domain="electric")
    anchor = node.add_anchor("A", domain="electric")
    if anchor_type:
        anchor.type = anchor_type
    return node, anchor


def test_dead_end_branch_off_a_junction_is_not_energized():
    """T: fonte numa ponta, terra na outra, terceiro braço sem saída.

    Por conectividade pura, os três braços formam um único componente —
    mas fisicamente só o braço fonte-terra conduz. O braço morto (dead)
    não deve ser marcado como energizado, mesmo estando fisicamente ligado
    ao ponto de junção que está energizado.
    """
    source_node, source = _terminal("src", anchor_type="source")
    ground_node, ground = _terminal("gnd", anchor_type="ground")
    junction_node, junction = _terminal("junction")
    dead_node, dead = _terminal("dead")

    c1 = Connection(source, junction)
    c2 = Connection(junction, ground)
    c3 = Connection(junction, dead)

    nodes = {"src": source_node, "gnd": ground_node, "junction": junction_node, "dead": dead_node}
    connections = {c.id: c for c in (c1, c2, c3)}
    engine = SimulationEngine(nodes, connections)

    engine._update_electric_domain()

    assert source.state is True
    assert junction.state is True
    assert ground.state is True
    assert dead.state is False


def test_parallel_branches_reconverging_are_both_energized():
    """Dois ramos em paralelo entre a fonte e o ponto de reconvergência —
    o padrão típico de contatos paralelos em escada de relé. Ambos os ramos
    devem conduzir.
    """
    source_node, source = _terminal("src", anchor_type="source")
    ground_node, ground = _terminal("gnd", anchor_type="ground")
    branch_a_node, branch_a = _terminal("branch_a")
    branch_b_node, branch_b = _terminal("branch_b")
    merge_node, merge = _terminal("merge")

    c1 = Connection(source, branch_a)
    c2 = Connection(source, branch_b)
    c3 = Connection(branch_a, merge)
    c4 = Connection(branch_b, merge)
    c5 = Connection(merge, ground)

    nodes = {n.id: n for n in (source_node, ground_node, branch_a_node, branch_b_node, merge_node)}
    connections = {c.id: c for c in (c1, c2, c3, c4, c5)}
    engine = SimulationEngine(nodes, connections)

    engine._update_electric_domain()

    assert branch_a.state is True
    assert branch_b.state is True
    assert merge.state is True


def test_source_and_ground_directly_facing_each_other_in_a_diamond_are_energized():
    """Dois contatos independentes do mesmo relé, fechados ao mesmo tempo, cada
    um completando sozinho um caminho fonte->terra (ex: o self-hold de K e o
    contato de potência que alimenta a bobina Y do mesmo relé). Isso faz fonte
    e terra caírem no MESMO bloco 2-aresta-conexo (dois caminhos paralelos
    entre eles) -- caso que o dead-end test não cobre, já que lá fonte e terra
    ficam em blocos diferentes.
    """
    source_node, source = _terminal("src", anchor_type="source")
    ground_node, ground = _terminal("gnd", anchor_type="ground")
    branch_a_node, branch_a = _terminal("branch_a")
    branch_b_node, branch_b = _terminal("branch_b")

    c1 = Connection(source, branch_a)
    c2 = Connection(branch_a, ground)
    c3 = Connection(source, branch_b)
    c4 = Connection(branch_b, ground)

    nodes = {n.id: n for n in (source_node, ground_node, branch_a_node, branch_b_node)}
    connections = {c.id: c for c in (c1, c2, c3, c4)}
    engine = SimulationEngine(nodes, connections)

    engine._update_electric_domain()

    assert source.state is True
    assert ground.state is True
    assert branch_a.state is True
    assert branch_b.state is True


def test_chained_diamonds_do_not_blow_up_combinatorially():
    """N diamantes (ramos paralelos reconvergindo) em série — o padrão real
    de uma escada de relé com N degraus de contatos paralelos. O algoritmo
    antigo (DFS sem memoização) era O(2^N); precisa completar em tempo linear.
    """
    n_diamonds = 40

    nodes = {}
    connections = {}

    def add_conn(a, b):
        c = Connection(a, b)
        connections[c.id] = c

    source_node, current = _terminal("src", anchor_type="source")
    nodes["src"] = source_node

    for i in range(n_diamonds):
        a_node, a = _terminal(f"a{i}")
        b_node, b = _terminal(f"b{i}")
        merge_node, merge = _terminal(f"merge{i}")
        nodes[f"a{i}"] = a_node
        nodes[f"b{i}"] = b_node
        nodes[f"merge{i}"] = merge_node

        add_conn(current, a)
        add_conn(current, b)
        add_conn(a, merge)
        add_conn(b, merge)
        current = merge

    ground_node, ground = _terminal("gnd", anchor_type="ground")
    nodes["gnd"] = ground_node
    add_conn(current, ground)

    engine = SimulationEngine(nodes, connections)

    start = time.perf_counter()
    engine._update_electric_domain()
    elapsed = time.perf_counter() - start

    assert elapsed < 2.0
    assert ground.state is True
    assert current.state is True  # último merge, adjacente ao ground


# --------------------------------------------------------------------------
# Load actuation: a coil actuates only with a voltage across it (T and B at
# different potentials on some source->ground path), not merely because
# both of its anchors are energized.
# --------------------------------------------------------------------------

from simulation.nodes.coil import Coil
from simulation.nodes.switch.contact import Contact


class _Circuit:
    """Builds a test circuit from terminals, coils, contacts and wires."""

    def __init__(self):
        self.nodes = {}
        self.connections = {}

    def terminal(self, node_id, anchor_type=None):
        node, anchor = _terminal(node_id, anchor_type)
        self.nodes[node_id] = node
        return anchor

    def _two_terminal(self, node):
        node.add_anchor("T", domain="electric")
        node.add_anchor("B", domain="electric")
        self.nodes[node.id] = node
        return node

    def coil(self, node_id):
        return self._two_terminal(Coil(node_id, domain="electric"))

    def contact(self, node_id, contact_type):
        return self._two_terminal(
            Contact(node_id, domain="electric", properties={"contact_type": contact_type})
        )

    def wire(self, a, b):
        c = Connection(a, b)
        self.connections[c.id] = c

    def place(self, part, a, b):
        """Wires a two-terminal node's T to `a` and B to `b`."""
        self.wire(a, part.anchors["T"])
        self.wire(part.anchors["B"], b)

    def run(self):
        engine = SimulationEngine(self.nodes, self.connections)
        engine.run_until_stable()
        return engine


def test_coil_with_both_terminals_on_one_point_does_not_actuate():
    """K has T and B on the same point A of an active path: no voltage across it."""
    c = _Circuit()
    src, gnd, a = c.terminal("src", "source"), c.terminal("gnd", "ground"), c.terminal("A")
    k, load = c.coil("K"), c.coil("L")
    c.wire(src, a)
    c.place(k, a, a)
    c.place(load, a, gnd)
    c.run()

    assert k.energized == 0
    assert load.energized == 1
    # No current through K: its wires read like a dead-end branch.
    assert a.state is True
    assert k.anchors["T"].state is False
    assert k.anchors["B"].state is False


def test_coil_parallel_to_closed_contact_does_not_actuate_until_it_opens():
    """K in parallel with an NC contact, in series with L. The closed NC
    equalizes K's terminals; opening it puts K and L in series."""
    c = _Circuit()
    src, gnd = c.terminal("src", "source"), c.terminal("gnd", "ground")
    a, b = c.terminal("A"), c.terminal("B")
    k, load, nc = c.coil("K"), c.coil("L"), c.contact("NC", "NC")
    c.wire(src, a)
    c.place(k, a, b)
    c.place(nc, a, b)
    c.place(load, b, gnd)
    engine = c.run()

    assert k.energized == 0
    assert load.energized == 1
    # Current goes through the NC, not through K.
    assert nc.anchors["T"].state is True
    assert nc.anchors["B"].state is True
    assert k.anchors["T"].state is False
    assert k.anchors["B"].state is False

    nc.handle_command({"type": "switch", "value": 1})
    engine.run_until_stable()

    assert k.energized == 1
    assert load.energized == 1
    assert k.anchors["T"].state is True
    assert k.anchors["B"].state is True


def test_coil_parallel_to_a_wire_does_not_actuate():
    c = _Circuit()
    src, gnd = c.terminal("src", "source"), c.terminal("gnd", "ground")
    a, b = c.terminal("A"), c.terminal("B")
    k, load = c.coil("K"), c.coil("L")
    c.place(load, src, a)
    c.place(k, a, b)
    c.wire(a, b)
    c.wire(b, gnd)
    c.run()

    assert k.energized == 0
    assert load.energized == 1
    assert k.anchors["T"].state is False
    assert k.anchors["B"].state is False


def test_two_coils_in_parallel_between_distinct_points_both_actuate():
    c = _Circuit()
    src, gnd = c.terminal("src", "source"), c.terminal("gnd", "ground")
    a, b = c.terminal("A"), c.terminal("B")
    k1, k2 = c.coil("K1"), c.coil("K2")
    c.wire(src, a)
    c.place(k1, a, b)
    c.place(k2, a, b)
    c.wire(b, gnd)
    c.run()

    assert k1.energized == 1
    assert k2.energized == 1


def test_two_coils_in_series_both_actuate():
    """No voltage division in the model: series loads all actuate."""
    c = _Circuit()
    src, gnd, mid = c.terminal("src", "source"), c.terminal("gnd", "ground"), c.terminal("M")
    k1, k2 = c.coil("K1"), c.coil("K2")
    c.place(k1, src, mid)
    c.place(k2, mid, gnd)
    c.run()

    assert k1.energized == 1
    assert k2.energized == 1


def test_load_loop_hanging_off_a_single_point_does_not_actuate():
    """Three coils in a ring hanging off a single point (source side, then
    ground side). Biconnected blocks split at the articulation point;
    bridge-separated components would not."""
    for hang_off in ("src", "gnd"):
        c = _Circuit()
        rails = {"src": c.terminal("src", "source"), "gnd": c.terminal("gnd", "ground")}
        x, y = c.terminal("X"), c.terminal("Y")
        load = c.coil("L")
        ring = [c.coil(f"R{i}") for i in range(3)]
        c.place(load, rails["src"], rails["gnd"])
        p = rails[hang_off]
        c.place(ring[0], p, x)
        c.place(ring[1], x, y)
        c.place(ring[2], y, p)
        c.run()

        assert load.energized == 1, hang_off
        assert [r.energized for r in ring] == [0, 0, 0], hang_off
        assert x.state is False and y.state is False, hang_off


def test_coil_between_two_sources_or_two_grounds_does_not_actuate():
    """All sources share one potential, and so do all grounds."""
    c = _Circuit()
    s1, s2 = c.terminal("s1", "source"), c.terminal("s2", "source")
    g1, g2 = c.terminal("g1", "ground"), c.terminal("g2", "ground")
    k_src, k_gnd, load = c.coil("K_src"), c.coil("K_gnd"), c.coil("L")
    c.place(k_src, s1, s2)
    c.place(load, s2, g1)
    c.place(k_gnd, g1, g2)
    c.run()

    assert k_src.energized == 0
    assert k_gnd.energized == 0
    assert load.energized == 1
    for k in (k_src, k_gnd):
        assert k.anchors["T"].state is False
        assert k.anchors["B"].state is False


def test_shorted_supply_powers_no_load():
    c = _Circuit()
    src, gnd = c.terminal("src", "source"), c.terminal("gnd", "ground")
    k = c.coil("K")
    c.wire(src, gnd)
    c.place(k, src, gnd)
    c.run()

    assert k.energized == 0


def test_load_decision_handles_a_long_series_chain():
    """Iterative DFS: a 3000-coil chain would overflow a recursive one."""
    c = _Circuit()
    current = c.terminal("src", "source")
    coils = []
    for i in range(3000):
        nxt = c.terminal(f"m{i}")
        coils.append(c.coil(f"K{i}"))
        c.place(coils[-1], current, nxt)
        current = nxt
    c.wire(current, c.terminal("gnd", "ground"))
    engine = SimulationEngine(c.nodes, c.connections)

    start = time.perf_counter()
    powered = engine._compute_powered_electric_loads()
    elapsed = time.perf_counter() - start

    assert elapsed < 2.0
    assert powered == set(coils)
