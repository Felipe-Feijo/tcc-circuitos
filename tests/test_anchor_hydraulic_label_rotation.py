import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QGraphicsScene

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.check_valve.check_valve import CheckValve


def make_node_in_scene():
    scene = QGraphicsScene()
    node = CheckValve(domain="hydraulic")
    scene.addItem(node)
    return scene, node


def test_label_sits_left_of_x_anchor_at_default_rotation():
    """X é a âncora esquerda do sprite (ver check_valve.py) -- o label
    deve crescer mais pra esquerda ainda, não sobrepor o corpo."""
    scene, node = make_node_in_scene()
    x_anchor = node.anchors["X"]
    label = x_anchor._label_hydraulic
    assert label.scenePos().x() < x_anchor.scenePos().x()


def test_label_sits_right_of_y_anchor_at_default_rotation():
    scene, node = make_node_in_scene()
    y_anchor = node.anchors["Y"]
    label = y_anchor._label_hydraulic
    assert label.scenePos().x() > y_anchor.scenePos().x()


def test_label_repositions_above_x_anchor_after_90_degree_rotation():
    """Depois de girar 90° no sentido horário, X (antes na esquerda) fica
    no topo -- o label deve passar a crescer PRA CIMA (y menor), não mais
    pro lado, senão fica sobreposto ao sprite rotacionado."""
    scene, node = make_node_in_scene()
    node.rotate(90)
    x_anchor = node.anchors["X"]
    label = x_anchor._label_hydraulic
    assert label.scenePos().y() < x_anchor.scenePos().y()


def test_label_repositions_below_y_anchor_after_90_degree_rotation():
    scene, node = make_node_in_scene()
    node.rotate(90)
    y_anchor = node.anchors["Y"]
    label = y_anchor._label_hydraulic
    assert label.scenePos().y() > y_anchor.scenePos().y()


def test_reposition_hydraulic_label_changes_local_pos_on_rotate():
    scene, node = make_node_in_scene()
    x_anchor = node.anchors["X"]
    label = x_anchor._label_hydraulic
    pos_before = label.pos()

    node.rotate(90)

    assert label.pos() != pos_before


def test_label_counter_rotates_to_stay_upright_after_rotation():
    """A posição do label acompanha a rotação do node (testes acima),
    mas a ORIENTAÇÃO do texto em si deve ficar sempre reta -- cancelada
    pela contra-rotação em NodeItem._counter_rotate_labels(), não pela
    ItemIgnoresTransformations (que também travaria o zoom)."""
    scene, node = make_node_in_scene()
    node.rotate(90)
    x_anchor = node.anchors["X"]
    label = x_anchor._label_hydraulic
    assert label.rotation() == -90.0


def test_label_counter_rotation_accumulates_correctly_across_multiple_rotations():
    scene, node = make_node_in_scene()
    node.rotate(90)
    node.rotate(90)
    node.rotate(90)  # node.rotation() agora é 270
    x_anchor = node.anchors["X"]
    label = x_anchor._label_hydraulic
    assert node.rotation() == 270
    assert label.rotation() == -270.0
