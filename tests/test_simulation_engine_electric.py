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
