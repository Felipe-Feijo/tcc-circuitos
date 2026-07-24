import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication, QMenu

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways
from graphics.items.base.nodes.directional_valve.directional_valve_item import DirectionalValveItem


class _ThreePositionItem(DirectionalValveItem):
    """Subclasse mínima só para exercitar THREE_POSITION=True neste teste --
    reaproveita sprites da 4/2 só para ter algo para carregar (Valve_4_3_Ways,
    criada na Task 4, é a versão de produção disso)."""
    THREE_POSITION = True
    node_type = "test_three_position_item"
    simulation_cls = None
    BODY_VISUALS = {
        0: {"sprite": "resources/nodes/valve_4_2_ways/valve_4_2_body_right.png", "offset": QPointF(0, 0)},
        1: {"sprite": "resources/nodes/valve_4_2_ways/valve_4_2_body_right.png", "offset": QPointF(0, 0)},
        2: {"sprite": "resources/nodes/valve_4_2_ways/valve_4_2_body_left.png",  "offset": QPointF(147, 0)},
    }

    def initialize_anchors(self):
        pass


def test_two_position_item_unaffected_default_false():
    item = Valve_4_2_Ways(domain="pneumatic")
    assert item.THREE_POSITION is False


def test_two_position_item_still_offers_spring_and_renamed_menu_with_2_options():
    item = Valve_4_2_Ways(domain="pneumatic")
    menu = QMenu()
    item._populate_actuator_menu(menu, side="left")
    labels = [a.text() for a in menu.actions()]
    assert "Spring" in labels

    full_menu = QMenu()
    item.extend_context_menu(full_menu)
    submenu_titles = [a.text() for a in full_menu.actions() if a.menu()]
    assert "Posição padrão" in submenu_titles
    assert "Posição de repouso" not in submenu_titles

    rest_menu = next(a.menu() for a in full_menu.actions() if a.text() == "Posição padrão")
    option_labels = [a.text() for a in rest_menu.actions()]
    assert option_labels == ["Direita (0)", "Esquerda (1)"]


def test_three_position_item_offers_renamed_menu_with_3_options_and_no_spring():
    item = _ThreePositionItem(domain="pneumatic")

    menu = QMenu()
    item._populate_actuator_menu(menu, side="left")
    labels = [a.text() for a in menu.actions()]
    assert "Spring" not in labels

    full_menu = QMenu()
    item.extend_context_menu(full_menu)
    submenu_titles = [a.text() for a in full_menu.actions() if a.menu()]
    assert "Posição padrão" in submenu_titles

    rest_menu = next(a.menu() for a in full_menu.actions() if a.text() == "Posição padrão")
    option_labels = [a.text() for a in rest_menu.actions()]
    assert option_labels == ["Direita (0)", "Centro (1)", "Esquerda (2)"]


def test_three_position_item_defaults_to_center_when_default_side_absent():
    item = _ThreePositionItem(domain="pneumatic")
    assert item.body_state == 1


def test_three_position_item_respects_default_side_property_for_initial_appearance():
    item = _ThreePositionItem(domain="pneumatic")
    item.properties["default_side"] = "left"
    item.initialize_body_visuals()
    assert item.body_state == 2

    item.properties["default_side"] = "right"
    item.initialize_body_visuals()
    assert item.body_state == 0

    item.properties["default_side"] = "center"
    item.initialize_body_visuals()
    assert item.body_state == 1
