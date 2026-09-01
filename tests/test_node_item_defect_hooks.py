import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QMenu

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.node_item import NodeItem
from graphics.utils.defect_dialog import DefectDialog


class _FakeDomainNode:
    def __init__(self, defect_active=False):
        self.anchors = {}
        self.defect_active = defect_active


class _DefectCapableItem(NodeItem):
    """Item mínimo que declara um DefectDialog, para exercitar os hooks."""
    node_type = "test_defect_item"
    simulation_cls = None

    def build_defect_dialog(self):
        return DefectDialog(title="Test defect")

    def apply_defect_from_dialog(self, dialog):
        self.command.emit(self.id, {"action": "set_defect", "k": 1.0, "stuck": False})


def test_default_node_item_has_no_defect_dialog():
    item = NodeItem(domain="hydraulic")
    assert item.build_defect_dialog() is None


def test_context_menu_shows_propriedades_when_not_simulating():
    item = _DefectCapableItem(domain="hydraulic")
    item.simulation_mode = False
    menu = QMenu()
    item.extend_context_menu(menu)
    labels = [a.text() for a in menu.actions()]
    assert "Properties..." in labels
    assert "Simulate defect..." not in labels


def test_context_menu_shows_simular_defeito_when_simulating():
    item = _DefectCapableItem(domain="hydraulic")
    item.simulation_mode = True
    menu = QMenu()
    item.extend_context_menu(menu)
    labels = [a.text() for a in menu.actions()]
    assert "Simulate defect..." in labels
    assert "Properties..." not in labels


def test_context_menu_hides_simular_defeito_when_item_has_no_defect_dialog():
    item = NodeItem(domain="hydraulic")
    item.simulation_mode = True
    menu = QMenu()
    item.extend_context_menu(menu)
    labels = [a.text() for a in menu.actions()]
    assert "Simulate defect..." not in labels


def test_update_from_domain_caches_domain_node_reference():
    item = NodeItem(domain="hydraulic")
    domain_node = _FakeDomainNode()
    item.update_from_domain(domain_node)
    assert item._domain_node is domain_node


def test_update_from_domain_sets_defect_indicator_true():
    item = NodeItem(domain="hydraulic")
    item.update_from_domain(_FakeDomainNode(defect_active=True))
    assert item._defect_indicator is True


def test_update_from_domain_sets_defect_indicator_false():
    item = NodeItem(domain="hydraulic")
    item.update_from_domain(_FakeDomainNode(defect_active=False))
    assert item._defect_indicator is False


def test_reset_visual_state_clears_domain_node_and_indicator():
    item = NodeItem(domain="hydraulic")
    item.update_from_domain(_FakeDomainNode(defect_active=True))
    item.reset_visual_state()
    assert item._domain_node is None
    assert item._defect_indicator is False
