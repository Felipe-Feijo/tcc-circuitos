import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QMenu

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways


def test_two_position_item_unaffected_default_false():
    item = Valve_4_2_Ways(domain="pneumatic")
    assert item.THREE_POSITION is False


def test_two_position_item_still_offers_spring_and_rest_menu():
    item = Valve_4_2_Ways(domain="pneumatic")
    menu = QMenu()
    item._populate_actuator_menu(menu, side="left")
    labels = [a.text() for a in menu.actions()]
    assert "Spring" in labels

    full_menu = QMenu()
    item.extend_context_menu(full_menu)
    submenu_titles = [a.text() for a in full_menu.actions() if a.menu()]
    assert "Posição de repouso" in submenu_titles
