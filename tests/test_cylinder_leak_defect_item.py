import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from main_window.language import language_manager
from tests.defect_test_helpers import form_label_texts
from graphics.items.base.nodes.cylinder.double_acting_cylinder import (
    DoubleActingCylinder as DoubleItem,
)
from graphics.items.base.nodes.cylinder.single_acting_cylinder import (
    SingleActingCylinder as SingleItem,
)
from simulation.nodes.cylinder.double_acting_cylinder import DoubleActingCylinder

ITEMS = [DoubleItem, SingleItem]
LABEL = "Internal leakage c_L (m³/s/Pa)"


@pytest.mark.parametrize("cls", ITEMS)
def test_hydraulic_offers_one_leak_field(cls):
    specs = cls(domain="hydraulic").defect_fields()
    assert [s.key for s in specs] == ["leak"]
    assert specs[0].kind == "number"
    assert specs[0].min_value is None
    assert specs[0].label == LABEL
    assert specs[0].placeholder == "ex: 1e-12  (≈ 0.6 L/min @ 100 bar)"


@pytest.mark.parametrize("cls", ITEMS)
def test_pneumatic_offers_no_defect(cls):
    assert cls(domain="pneumatic").defect_fields() == []


def _node():
    node = DoubleActingCylinder(
        "cyl", domain="hydraulic",
        properties={"bore": 0.05, "rod_diameter": 0.02, "stroke": 0.2},
    )
    node.add_anchor("A", domain="hydraulic")
    node.add_anchor("B", domain="hydraulic")
    return node


def test_dialog_prefilled_from_live_node():
    item = DoubleItem(domain="hydraulic")
    node = _node()
    item.update_from_domain(node)
    node.handle_command({"action": "set_defect", "leak": 2e-12})
    dialog = item.build_defect_dialog()
    assert float(dialog.defect_widget("leak").text()) == 2e-12


def test_apply_emits_set_defect_float():
    item = DoubleItem(domain="hydraulic")
    item.update_from_domain(_node())
    dialog = item.build_defect_dialog()
    dialog.defect_widget("leak").setText("3e-12")
    received = []
    item.command.connect(lambda nid, payload: received.append(payload))
    item.apply_defect_from_dialog(dialog)
    assert received == [{"action": "set_defect", "leak": 3e-12}]


def test_label_translates_to_pt_br():
    item = SingleItem(domain="hydraulic")
    language_manager.apply_language(app, "pt_BR")
    try:
        dialog = item.build_defect_dialog()
        try:
            assert "Vazamento interno c_L (m³/s/Pa)" in form_label_texts(dialog)
        finally:
            dialog.close()
    finally:
        language_manager.apply_language(app, "en")


def test_velocity_label_uses_piston_velocity():
    item = DoubleItem(domain="hydraulic")
    node = _node()
    node.c_leak = 1e-11
    node.anchors["A"].flow = 1e-4
    node.anchors["A"].pressure = 3e6
    node.anchors["B"].pressure = 0.0
    shown = []
    item.update_velocity_label = shown.append
    item._update_velocity_from_domain(node)
    assert shown == [pytest.approx((1e-4 - 1e-11 * 3e6) / node.area_a)]


def test_velocity_label_skips_error_strings():
    item = DoubleItem(domain="hydraulic")
    node = _node()
    node.anchors["A"].flow = "ERR"
    shown = []
    item.update_velocity_label = shown.append
    item._update_velocity_from_domain(node)
    assert shown == []
