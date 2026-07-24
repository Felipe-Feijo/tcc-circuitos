import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QMenu

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.directional_valve.valve_4_3_ways import Valve_4_3_Ways
from simulation.nodes.directional_valve.valve_4_3_ways import Valve_4_3_Ways as Valve_4_3_WaysNode


def test_palette_meta_includes_both_domains():
    meta = Valve_4_3_Ways.palette_meta()
    assert meta.domains == ("pneumatic", "hydraulic")
    assert meta.name == "Valve 4/3 Ways"


def test_simulation_cls_linkage():
    assert Valve_4_3_Ways.simulation_cls is Valve_4_3_WaysNode


def test_three_position_flag_set():
    assert Valve_4_3_Ways.THREE_POSITION is True


def test_body_visuals_has_three_states_with_confirmed_offsets():
    # Offsets são relativos ao centro (state 1), que é a referência (0) --
    # não ao state 0, diferente do padrão da 4/2 vias. Direita e esquerda
    # deslocam em sentidos opostos a partir do centro (sinais opostos).
    node = Valve_4_3_Ways(domain="pneumatic")
    assert set(node.BODY_VISUALS.keys()) == {0, 1, 2}
    assert node.BODY_VISUALS[0]["offset"].x() == -150
    assert node.BODY_VISUALS[1]["offset"].x() == 0
    assert node.BODY_VISUALS[2]["offset"].x() == 147


def test_initial_body_state_is_center():
    node = Valve_4_3_Ways(domain="pneumatic")
    assert node.body_state == 1


def test_anchors_p_a_b_r_present():
    node = Valve_4_3_Ways(domain="pneumatic")
    assert set(node.anchors.keys()) == {"P", "A", "B", "R"}
    assert node.anchors["A"].pos().y() == 0
    assert node.anchors["B"].pos().y() == 0
    assert node.anchors["P"].pos().y() == node.height
    assert node.anchors["R"].pos().y() == node.height


def test_default_position_menu_renamed_with_3_options():
    node = Valve_4_3_Ways(domain="pneumatic")
    menu = QMenu()
    node.extend_context_menu(menu)
    submenu_titles = [a.text() for a in menu.actions() if a.menu()]
    assert "Posição padrão" in submenu_titles
    assert "Posição de repouso" not in submenu_titles

    rest_menu = next(a.menu() for a in menu.actions() if a.text() == "Posição padrão")
    option_labels = [a.text() for a in rest_menu.actions()]
    assert option_labels == ["Direita (0)", "Centro (1)", "Esquerda (2)"]


def test_spring_excluded_from_actuator_menu():
    node = Valve_4_3_Ways(domain="pneumatic")
    menu = QMenu()
    node._populate_actuator_menu(menu, side="left")
    labels = [a.text() for a in menu.actions()]
    assert "Spring" not in labels


def test_bounding_rect_covers_every_state_including_negative_offset():
    # state 0 (direita) tem offset negativo (-150) -- o body é pintado à
    # esquerda de x=0 nesse estado. boundingRect() precisa cobrir isso ou o
    # Qt deixa rastros de repintura fora da área declarada (bug real
    # encontrado após o usuário ver o render com os 3 estados).
    node = Valve_4_3_Ways(domain="pneumatic")
    bounds = node.boundingRect()
    for visual in node.BODY_VISUALS.values():
        offset_x = visual["offset"].x()
        assert bounds.left() <= offset_x
        assert bounds.right() >= offset_x + node.width
