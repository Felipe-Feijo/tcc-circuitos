import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.nodes.check_valve.check_valve import CheckValve


def make_node(piloted=False, with_z_anchor=None):
    """with_z_anchor: força a criação da anchor Z mesmo com piloted=False,
    pra testar que a propriedade (não a mera presença da anchor) controla
    a lógica de força."""
    node = CheckValve("n1", domain="pneumatic", properties={"piloted": piloted})
    node.add_anchor("X", domain="pneumatic")
    node.add_anchor("Y", domain="pneumatic")
    if piloted or with_z_anchor:
        node.add_anchor("Z", domain="pneumatic")
    return node


def test_free_flow_y_true_x_false_connects():
    node = make_node()
    node.anchors["X"].state = False
    node.anchors["Y"].state = True
    node.post_step_update(dt=0.1)
    assert node.get_internal_connections() == [("X", "Y")]
    assert node.get_visual_state() == "open"


def test_blocked_x_true_y_false_does_not_connect():
    node = make_node()
    node.anchors["X"].state = True
    node.anchors["Y"].state = False
    node.post_step_update(dt=0.1)
    assert node.get_internal_connections() == []
    assert node.get_visual_state() == "closed"


def test_both_zero_does_not_connect():
    node = make_node()
    node.anchors["X"].state = False
    node.anchors["Y"].state = False
    node.post_step_update(dt=0.1)
    assert node.get_internal_connections() == []
    assert node.get_visual_state() == "closed"


def test_both_one_connects():
    node = make_node()
    node.anchors["X"].state = True
    node.anchors["Y"].state = True
    node.post_step_update(dt=0.1)
    assert node.get_internal_connections() == [("X", "Y")]
    assert node.get_visual_state() == "open"


def test_pilot_forces_open_even_when_y_false():
    node = make_node(piloted=True)
    node.anchors["X"].state = True
    node.anchors["Y"].state = False
    node.anchors["Z"].state = True
    node.post_step_update(dt=0.1)
    assert node.get_internal_connections() == [("X", "Y")]
    assert node.get_visual_state() == "open"


def test_piloted_false_ignores_z_state_even_if_anchor_present():
    node = make_node(piloted=False, with_z_anchor=True)
    node.anchors["X"].state = True
    node.anchors["Y"].state = False
    node.anchors["Z"].state = True
    node.post_step_update(dt=0.1)
    assert node.get_internal_connections() == []
    assert node.get_visual_state() == "closed"


def test_get_state_and_set_state_roundtrip():
    node = make_node()
    node.anchors["X"].state = False
    node.anchors["Y"].state = True
    node.post_step_update(dt=0.1)
    state = node.get_state()

    node2 = make_node()
    node2.set_state(state)
    assert node2.get_internal_connections() == [("X", "Y")]
    assert node2.get_visual_state() == "open"
