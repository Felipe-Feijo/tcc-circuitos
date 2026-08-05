"""Regressão: menu de contexto ficava totalmente inacessível durante a
simulação (EditorMode.SIMULATE), porque DiagramItemBase.contextMenuEvent só
permitia EditorMode.SELECT -- isso bloqueava "Simular defeito..." (e
qualquer outra entrada ciente de simulação) antes mesmo de
extend_context_menu() ser chamado.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QMenu, QGraphicsScene
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QPoint

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


def test_context_menu_event_returns_early_when_no_editor_attached():
    item = Valve_4_2_Ways(domain="hydraulic")

    class FakeEvent:
        def __init__(self):
            self.ignored = False
        def ignore(self):
            self.ignored = True

    ev = FakeEvent()
    item.contextMenuEvent(ev)  # não deve levantar (editor is None)
    # self.editor is None -- retorna antes até de chamar ignore()/accept().
    assert ev.ignored is False


class _FakeContextMenuEvent:
    """Substituto mínimo de QGraphicsSceneContextMenuEvent (que o PyQt6 não
    permite instanciar diretamente) para exercitar contextMenuEvent() por
    inteiro sem abrir um QMenu real (menu.exec() é monkeypatchado)."""

    def __init__(self):
        self.ignored = False
        self.accepted = False

    def ignore(self):
        self.ignored = True

    def accept(self):
        self.accepted = True

    def screenPos(self):
        return QPoint(0, 0)


def test_context_menu_event_end_to_end_offers_defect_not_delete_during_simulation(monkeypatch):
    """Prova a costura entre _context_menu_allowed(), a exclusão de
    "Deletar" e extend_context_menu() -- a parte que os testes acima (que
    chamam extend_context_menu() diretamente) não cobrem."""
    exec_calls = []
    monkeypatch.setattr(QMenu, "exec", lambda self, pos: exec_calls.append(_menu_labels(self)) or None)

    scene = QGraphicsScene()
    item = Valve_4_2_Ways(domain="hydraulic")
    item.properties["k"] = 1e-7
    item.simulation_mode = True
    scene.addItem(item)

    editor = EditorState()
    editor.mode = EditorMode.SIMULATE
    editor.actions = {"delete": QAction("Deletar")}
    item.editor = editor

    ev = _FakeContextMenuEvent()
    item.contextMenuEvent(ev)

    assert ev.accepted is True
    assert len(exec_calls) == 1
    labels = exec_calls[0]
    assert "Simular defeito..." in labels
    assert "Deletar" not in labels


def test_context_menu_event_end_to_end_ignores_when_menu_would_be_empty(monkeypatch):
    """Item sem build_defect_dialog (a maioria) não deve abrir um popup
    vazio durante a simulação -- ver Issue #1 da revisão desta correção."""
    exec_calls = []
    monkeypatch.setattr(QMenu, "exec", lambda self, pos: exec_calls.append(True) or None)

    scene = QGraphicsScene()
    item = ButtonSwitch(domain="electric")
    item.simulation_mode = True
    scene.addItem(item)

    editor = EditorState()
    editor.mode = EditorMode.SIMULATE
    editor.actions = {"delete": QAction("Deletar")}
    item.editor = editor

    ev = _FakeContextMenuEvent()
    item.contextMenuEvent(ev)

    assert exec_calls == []  # menu.exec() nunca chamado -- nada foi mostrado
    assert ev.ignored is True
    assert ev.accepted is False
    assert editor.active_context_menu is None


def test_context_menu_event_end_to_end_offers_delete_in_select_mode(monkeypatch):
    exec_calls = []
    monkeypatch.setattr(QMenu, "exec", lambda self, pos: exec_calls.append(_menu_labels(self)) or None)

    scene = QGraphicsScene()
    item = Valve_4_2_Ways(domain="hydraulic")
    item.properties["k"] = 1e-7
    item.simulation_mode = False
    scene.addItem(item)

    editor = EditorState()
    editor.mode = EditorMode.SELECT
    editor.actions = {"delete": QAction("Deletar")}
    item.editor = editor

    ev = _FakeContextMenuEvent()
    item.contextMenuEvent(ev)

    assert len(exec_calls) == 1
    assert "Deletar" in exec_calls[0]


def test_context_menu_event_ignores_in_add_mode():
    item = Valve_4_2_Ways(domain="hydraulic")
    editor = EditorState()
    editor.mode = EditorMode.ADD
    item.editor = editor

    ev = _FakeContextMenuEvent()
    item.contextMenuEvent(ev)

    assert ev.ignored is True
    assert ev.accepted is False


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
