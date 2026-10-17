import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from tests.defect_test_helpers import form_label_texts
from graphics.items.base.nodes.cylinder.double_acting_cylinder import (
    DoubleActingCylinder as DoubleItem,
)
from graphics.items.base.nodes.cylinder.single_acting_cylinder import (
    SingleActingCylinder as SingleItem,
)
from simulation.nodes.cylinder.double_acting_cylinder import DoubleActingCylinder
from simulation.nodes.cylinder.single_acting_cylinder import SingleActingCylinder

C = 1e-11
LABEL = "Internal leakage (m³/s/Pa)"
NODES = [
    (DoubleActingCylinder, {"bore": 0.05, "rod_diameter": 0.02, "stroke": 0.2}),
    (SingleActingCylinder, {"bore": 0.05, "stroke": 0.2, "spring_k": 5000.0}),
]
ITEMS = [DoubleItem, SingleItem]


@pytest.mark.parametrize("cls,props", NODES)
def test_node_defaults_to_zero_without_property(cls, props):
    assert cls("cyl", domain="hydraulic", properties=dict(props)).c_leak == 0.0


@pytest.mark.parametrize("cls,props", NODES)
def test_node_reads_leak_from_properties(cls, props):
    cyl = cls("cyl", domain="hydraulic", properties={**props, "c_leak": C})
    assert cyl.c_leak == pytest.approx(C)
    assert cyl.defect_active is False


@pytest.mark.parametrize("cls,props", NODES)
def test_node_none_or_negative_property_is_zero(cls, props):
    assert cls("cyl", domain="hydraulic", properties={**props, "c_leak": None}).c_leak == 0.0
    assert cls("cyl", domain="hydraulic", properties={**props, "c_leak": -C}).c_leak == 0.0


@pytest.mark.parametrize("cls,props", NODES)
def test_clear_defect_restores_configured_leak(cls, props):
    cyl = cls("cyl", domain="hydraulic", properties={**props, "c_leak": C})
    cyl.handle_command({"action": "set_defect", "leak": 5 * C})
    assert cyl.defect_active is True
    cyl.handle_command({"action": "clear_defect"})
    assert cyl.c_leak == pytest.approx(C)
    assert cyl.defect_active is False


@pytest.mark.parametrize("cls", ITEMS)
def test_item_defaults_property_to_zero(cls):
    assert cls(domain="hydraulic").properties["c_leak"] == 0.0


@pytest.mark.parametrize("cls", ITEMS)
def test_pneumatic_item_has_no_leak(cls):
    item = cls(domain="pneumatic")
    assert "c_leak" not in item.properties
    dialog = item.build_properties_dialog()
    try:
        assert LABEL not in form_label_texts(dialog)
    finally:
        dialog.close()


@pytest.mark.parametrize("cls", ITEMS)
def test_dialog_shows_optional_leak_field(cls):
    item = cls(domain="hydraulic")
    item.properties["c_leak"] = C
    dialog = item.build_properties_dialog()
    try:
        assert LABEL in form_label_texts(dialog)
        assert dialog._field_leak._is_required is False
        assert float(dialog._field_leak.text()) == pytest.approx(C)
    finally:
        dialog.close()


@pytest.mark.parametrize("cls", ITEMS)
@pytest.mark.parametrize("text,expected", [("2e-12", 2e-12), ("", 0.0)])
def test_apply_stores_leak(cls, text, expected):
    item = cls(domain="hydraulic")
    item.properties.update(bore=0.05, rod_diameter=0.02, stroke=0.2, spring_k=5000.0)
    dialog = item.build_properties_dialog()
    try:
        dialog._field_leak.setText(text)
        item.apply_properties_from_dialog(dialog)
    finally:
        dialog.close()
    assert item.properties["c_leak"] == pytest.approx(expected)
