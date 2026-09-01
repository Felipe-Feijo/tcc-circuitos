"""Confere build_defect_dialog()/apply_defect_from_dialog() promovidos pra
DirectionalValveItem (base compartilhada) -- todas as 5 válvulas direcionais
ganham "Simulate defect..." de uma vez, sem duplicar código por subtipo."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QMenu

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.directional_valve.valve_2_2_ways import Valve_2_2_Ways
from graphics.items.base.nodes.directional_valve.valve_3_2_ways import Valve_3_2_Ways
from graphics.items.base.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways
from graphics.items.base.nodes.directional_valve.valve_4_3_ways import Valve_4_3_Ways
from graphics.items.base.nodes.directional_valve.valve_5_2_ways import Valve_5_2_Ways

import pytest

ALL_VALVE_ITEM_CLASSES = [
    Valve_2_2_Ways, Valve_3_2_Ways, Valve_4_2_Ways, Valve_4_3_Ways, Valve_5_2_Ways,
]


@pytest.mark.parametrize("cls", ALL_VALVE_ITEM_CLASSES)
def test_pneumatic_valve_has_no_defect_dialog(cls):
    item = cls(domain="pneumatic")
    assert item.build_defect_dialog() is None


@pytest.mark.parametrize("cls", ALL_VALVE_ITEM_CLASSES)
def test_hydraulic_valve_defect_dialog_titled_after_palette_meta_name(cls):
    item = cls(domain="hydraulic")
    item.properties["k"] = 1e-7
    dialog = item.build_defect_dialog()
    assert dialog is not None
    assert cls.palette_meta().name in dialog.windowTitle()


@pytest.mark.parametrize("cls", ALL_VALVE_ITEM_CLASSES)
def test_hydraulic_valve_defect_dialog_prefills_k_from_properties(cls):
    item = cls(domain="hydraulic")
    item.properties["k"] = 2.5e-8
    dialog = item.build_defect_dialog()
    assert float(dialog._field_k.text()) == 2.5e-8


@pytest.mark.parametrize("cls", ALL_VALVE_ITEM_CLASSES)
def test_apply_defect_from_dialog_emits_set_defect(cls):
    item = cls(domain="hydraulic")
    item.properties["k"] = 1e-7
    dialog = item.build_defect_dialog()
    dialog._field_k.setText("3.3e-8")
    dialog._field_stuck.setChecked(True)

    received = []
    item.command.connect(lambda node_id, payload: received.append((node_id, payload)))
    item.apply_defect_from_dialog(dialog)

    assert received == [(item.id, {"action": "set_defect", "k": 3.3e-8, "stuck": True})]


@pytest.mark.parametrize("cls", ALL_VALVE_ITEM_CLASSES)
def test_apply_defect_from_dialog_emits_clear_defect_on_restore(cls):
    item = cls(domain="hydraulic")
    item.properties["k"] = 1e-7
    dialog = item.build_defect_dialog()
    dialog.restore_requested = True

    received = []
    item.command.connect(lambda node_id, payload: received.append((node_id, payload)))
    item.apply_defect_from_dialog(dialog)

    assert received == [(item.id, {"action": "clear_defect"})]


@pytest.mark.parametrize("cls", ALL_VALVE_ITEM_CLASSES)
def test_context_menu_during_simulation_offers_defect_entry_only(cls):
    item = cls(domain="hydraulic")
    item.properties["k"] = 1e-7
    item.simulation_mode = True

    menu = QMenu()
    item.extend_context_menu(menu)
    labels = [a.text() for a in menu.actions()]
    submenu_titles = [a.text() for a in menu.actions() if a.menu()]

    assert "Simulate defect..." in labels
    assert "Properties..." not in labels
    assert not submenu_titles  # nenhum submenu de atuador/posição durante simulação
