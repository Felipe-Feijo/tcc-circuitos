"""Every NodeItem gets a "Name" field prepended to its properties
dialog -- even node types with no properties of their own -- so the
user can always give a node a display name (see NodeItem.name)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.junction_node_item import JunctionNodeItem
from graphics.items.base.nodes.accumulator import Accumulator


def test_prep_properties_dialog_builds_a_dialog_for_a_node_with_no_own_properties():
    """JunctionNodeItem doesn't override build_properties_dialog() (base
    returns None) -- the wrapper must still produce a usable dialog."""
    item = JunctionNodeItem(domain="electric")

    dialog, name_field = item._prep_properties_dialog()

    assert dialog is not None
    assert name_field.text() == ""


def test_prep_properties_dialog_prefills_name_field_with_current_name():
    item = JunctionNodeItem(domain="electric")
    item.name = "Válvula X"

    _, name_field = item._prep_properties_dialog()

    assert name_field.text() == "Válvula X"


def test_prep_properties_dialog_name_field_is_first_row_above_subclass_fields():
    node = Accumulator(domain="hydraulic")

    dialog, name_field = node._prep_properties_dialog()

    first_field = dialog._form_layout.itemAt(0, dialog._form_layout.ItemRole.FieldRole).widget()
    assert first_field is name_field
    assert dialog._field_v0 is not None  # subclass field still present, just pushed down
