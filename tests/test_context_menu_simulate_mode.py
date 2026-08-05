"""Regressão: menu de contexto ficava totalmente inacessível durante a
simulação (EditorMode.SIMULATE), porque DiagramItemBase.contextMenuEvent só
permitia EditorMode.SELECT -- isso bloqueava "Simular defeito..." (e
qualquer outra entrada ciente de simulação) antes mesmo de
extend_context_menu() ser chamado.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QMenu

app = QApplication.instance() or QApplication([])

from editor.editor_state import EditorState
from editor.mode import EditorMode
from graphics.items.base.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways
from graphics.items.base.nodes.switch.button_switch import ButtonSwitch
from graphics.items.base.nodes.cylinder.double_acting_cylinder import DoubleActingCylinder


def _menu_labels(menu: QMenu) -> list[str]:
    return [a.text() for a in menu.actions()]


# ---------------------------------------------------------------------------
# _context_menu_allowed() -- o gate que estava bloqueando tudo em SIMULATE
# ---------------------------------------------------------------------------

def test_context_menu_allowed_in_select_mode():
    item = Valve_4_2_Ways(domain="hydraulic")
    item.editor = EditorState()
    item.editor.mode = EditorMode.SELECT
    assert item._context_menu_allowed() is True


def test_context_menu_allowed_in_simulate_mode():
    item = Valve_4_2_Ways(domain="hydraulic")
    item.editor = EditorState()
    item.editor.mode = EditorMode.SIMULATE
    assert item._context_menu_allowed() is True


def test_context_menu_blocked_in_add_mode():
    item = Valve_4_2_Ways(domain="hydraulic")
    item.editor = EditorState()
    item.editor.mode = EditorMode.ADD
    assert item._context_menu_allowed() is False


def test_context_menu_blocked_in_connect_mode():
    item = Valve_4_2_Ways(domain="hydraulic")
    item.editor = EditorState()
    item.editor.mode = EditorMode.CONNECT
    assert item._context_menu_allowed() is False


def test_context_menu_event_ignores_when_no_editor_attached():
    item = Valve_4_2_Ways(domain="hydraulic")

    class FakeEvent:
        def __init__(self):
            self.ignored = False
        def ignore(self):
            self.ignored = True

    ev = FakeEvent()
    item.contextMenuEvent(ev)  # não deve levantar (editor is None)
    assert ev.ignored is False  # early-return antes de tocar no evento


# ---------------------------------------------------------------------------
# extend_context_menu() -- "Simular defeito..." aparece, edição de projeto some
# ---------------------------------------------------------------------------

def test_hydraulic_valve_menu_during_simulation_offers_defect_only():
    item = Valve_4_2_Ways(domain="hydraulic")
    item.properties["k"] = 1e-7
    item.simulation_mode = True

    menu = QMenu()
    item.extend_context_menu(menu)
    labels = _menu_labels(menu)

    assert "Simular defeito..." in labels
    assert "Propriedades..." not in labels
    assert "Rotate 90°" not in labels
    assert "Adicionar label" not in labels


def test_hydraulic_valve_menu_during_simulation_hides_actuator_submenus():
    item = Valve_4_2_Ways(domain="hydraulic")
    item.properties["k"] = 1e-7
    item.simulation_mode = True

    menu = QMenu()
    item.extend_context_menu(menu)
    submenu_titles = [a.text() for a in menu.actions() if a.menu()]

    assert "Atuador esquerdo" not in submenu_titles
    assert "Atuador direito" not in submenu_titles
    assert "Posição padrão" not in submenu_titles


def test_hydraulic_valve_menu_outside_simulation_offers_full_editing():
    item = Valve_4_2_Ways(domain="hydraulic")
    item.properties["k"] = 1e-7
    item.simulation_mode = False

    menu = QMenu()
    item.extend_context_menu(menu)
    labels = _menu_labels(menu)
    submenu_titles = [a.text() for a in menu.actions() if a.menu()]

    assert "Propriedades..." in labels
    assert "Rotate 90°" in labels
    assert "Adicionar label" in labels
    assert "Simular defeito..." not in labels
    assert "Atuador esquerdo" in submenu_titles
    assert "Atuador direito" in submenu_titles
    assert "Posição padrão" in submenu_titles


def test_switch_item_hides_contact_type_submenu_during_simulation():
    item = ButtonSwitch(domain="electric")
    item.simulation_mode = True

    menu = QMenu()
    item.extend_context_menu(menu)
    submenu_titles = [a.text() for a in menu.actions() if a.menu()]

    assert "Tipo de contato" not in submenu_titles


def test_switch_item_shows_contact_type_submenu_outside_simulation():
    item = ButtonSwitch(domain="electric")
    item.simulation_mode = False

    menu = QMenu()
    item.extend_context_menu(menu)
    submenu_titles = [a.text() for a in menu.actions() if a.menu()]

    assert "Tipo de contato" in submenu_titles


def test_cylinder_item_hides_sensor_and_state_submenus_during_simulation():
    item = DoubleActingCylinder(domain="hydraulic")
    item.simulation_mode = True

    menu = QMenu()
    item.extend_context_menu(menu)
    submenu_titles = [a.text() for a in menu.actions() if a.menu()]

    assert "Sensor retraído" not in submenu_titles
    assert "Sensor estendido" not in submenu_titles
    assert "Estado inicial" not in submenu_titles


def test_cylinder_item_shows_sensor_and_state_submenus_outside_simulation():
    item = DoubleActingCylinder(domain="hydraulic")
    item.simulation_mode = False

    menu = QMenu()
    item.extend_context_menu(menu)
    submenu_titles = [a.text() for a in menu.actions() if a.menu()]

    assert "Sensor retraído" in submenu_titles
    assert "Sensor estendido" in submenu_titles
    assert "Estado inicial" in submenu_titles
