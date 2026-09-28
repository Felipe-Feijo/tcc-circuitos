"""NodeItem builds/applies the defect dialog generically from defect_fields()."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.node_item import NodeItem
from graphics.items.base.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways
from graphics.utils.defect_dialog import DefectFieldSpec
from simulation.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways as DomainValve_4_2_Ways


class _FakeDomainNode:
    def __init__(self, values):
        self.anchors = {}
        self.defect_active = False
        self._values = values

    def defect_value(self, key):
        return self._values.get(key)


class _Item(NodeItem):
    node_type = "test_generic_defect_item"
    simulation_cls = None

    def setup(self):
        self.properties = {}

    def defect_fields(self):
        return [
            DefectFieldSpec("k", "K", "number", min_value=0),
            DefectFieldSpec("stuck", "Stuck", "bool"),
            DefectFieldSpec("mode", "Mode", "choice", options=(("none", "Normal"), ("open", "Open"))),
        ]


def _emitted(item, dialog):
    received = []
    item.command.connect(lambda node_id, payload: received.append(payload))
    item.apply_defect_from_dialog(dialog)
    return received


def test_no_defect_fields_means_no_dialog():
    assert NodeItem(domain="hydraulic").build_defect_dialog() is None


def test_title_falls_back_to_class_name_without_palette_meta():
    dialog = _Item(domain="hydraulic").build_defect_dialog()
    assert dialog.windowTitle() == "Simulate defect — _Item"


def test_fields_prefilled_from_live_domain_node():
    item = _Item(domain="hydraulic")
    item.update_from_domain(_FakeDomainNode({"k": 9.9e-9, "stuck": True, "mode": "open"}))
    dialog = item.build_defect_dialog()
    assert float(dialog.defect_widget("k").text()) == 9.9e-9
    assert dialog.defect_widget("stuck").isChecked() is True
    assert dialog.defect_widget("mode").currentData() == "open"


def test_fields_prefilled_from_properties_before_first_sync():
    item = _Item(domain="hydraulic")
    item.properties["k"] = 2.5e-8
    dialog = item.build_defect_dialog()
    assert float(dialog.defect_widget("k").text()) == 2.5e-8
    assert dialog.defect_widget("stuck").isChecked() is False


def test_note_field_always_added_last():
    dialog = _Item(domain="hydraulic").build_defect_dialog()
    assert dialog.note_field is not None
    assert dialog._form_layout.rowCount() == 4


def test_apply_emits_set_defect_with_every_typed_value():
    item = _Item(domain="hydraulic")
    item.properties["k"] = 1e-7
    dialog = item.build_defect_dialog()
    dialog.defect_widget("stuck").setChecked(True)
    assert _emitted(item, dialog) == [
        {"action": "set_defect", "k": 1e-7, "stuck": True, "mode": "none"}
    ]


def test_apply_includes_note_only_when_given():
    item = _Item(domain="hydraulic")
    item.properties["k"] = 1e-7
    dialog = item.build_defect_dialog()
    dialog.note_field.setText("  debris ")
    assert _emitted(item, dialog)[0]["note"] == "debris"


def test_restore_emits_clear_defect_with_optional_note():
    item = _Item(domain="hydraulic")
    item.properties["k"] = 1e-7
    dialog = item.build_defect_dialog()
    dialog.restore_requested = True
    assert _emitted(item, dialog) == [{"action": "clear_defect"}]

    dialog.note_field.setText("fixed")
    item2 = _Item(domain="hydraulic")
    assert _emitted(item2, dialog) == [{"action": "clear_defect", "note": "fixed"}]


def test_valve_dialog_prefills_stuck_from_real_domain_node():
    """End-to-end with the real DefectMixin node (not a fake)."""
    item = Valve_4_2_Ways(domain="hydraulic")
    item.properties["k"] = 1e-7
    domain = DomainValve_4_2_Ways("v", domain="hydraulic", properties={"k": 1e-7})
    for port in ("P", "A", "B", "R"):
        domain.add_anchor(port, domain="hydraulic")
    domain.handle_command({"action": "set_defect", "k": 4e-8, "stuck": True})

    item.update_from_domain(domain)
    dialog = item.build_defect_dialog()
    assert float(dialog.defect_widget("k").text()) == 4e-8
    assert dialog.defect_widget("stuck").isChecked() is True
