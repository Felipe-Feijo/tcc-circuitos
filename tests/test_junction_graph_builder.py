"""Junction (domínio) deve se comportar como um Node pass-through comum:
GraphBuilder consegue instanciá-lo e ligar 3 conexões ao seu único anchor,
sem nenhum código especial em GraphBuilder ou nos solvers -- a lógica de
fan-out num Anchor já é genérica (ver test_simulation_engine_electric.py)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.nodes.nodes import Junction


def test_junction_is_a_pass_through_node_with_one_anchor():
    node = Junction("j1", domain="electric")
    anchor = node.add_anchor("J", domain="electric")

    assert node.type == "junction"
    assert node.get_internal_connections() == []
    node.update()  # não deve levantar nem mudar o estado do anchor
    assert anchor.state is False


def test_junction_anchor_accepts_three_connections():
    from simulation.connections import Connection

    j = Junction("j1", domain="electric")
    j_anchor = j.add_anchor("J", domain="electric")

    a = Junction("a", domain="electric").add_anchor("A", domain="electric")
    b = Junction("b", domain="electric").add_anchor("A", domain="electric")
    c = Junction("c", domain="electric").add_anchor("A", domain="electric")

    Connection(a, j_anchor)
    Connection(b, j_anchor)
    Connection(c, j_anchor)

    assert len(j_anchor.connections) == 3
