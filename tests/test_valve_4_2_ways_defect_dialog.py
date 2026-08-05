import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways


class _FakeDomainNode:
    def __init__(self, k, stuck=False):
        self.k = k
        self._stuck_defect = stuck
        self.anchors = {}
        self.defect_active = stuck
        self.bits = {"left": 0, "right": 0}  # Required by DirectionalValveItem.update_from_domain()
        self.body_state = 0  # Required by DirectionalValveItem.update_from_domain()


def test_pneumatic_valve_has_no_defect_dialog():
    item = Valve_4_2_Ways(domain="pneumatic")
    assert item.build_defect_dialog() is None


def test_hydraulic_valve_prefills_k_from_properties_before_any_simulation_step():
    item = Valve_4_2_Ways(domain="hydraulic")
    item.properties["k"] = 2.5e-8
    dialog = item.build_defect_dialog()
    assert dialog is not None
    assert float(dialog._field_k.text()) == 2.5e-8


def test_hydraulic_valve_prefills_k_from_live_domain_node_after_sync():
    item = Valve_4_2_Ways(domain="hydraulic")
    item.properties["k"] = 2.5e-8
    item.update_from_domain(_FakeDomainNode(k=9.9e-9))
    dialog = item.build_defect_dialog()
    assert float(dialog._field_k.text()) == 9.9e-9


def test_hydraulic_valve_prefills_stuck_checkbox_from_live_domain_node():
    item = Valve_4_2_Ways(domain="hydraulic")
    item.update_from_domain(_FakeDomainNode(k=1e-7, stuck=True))
    dialog = item.build_defect_dialog()
    assert dialog._field_stuck.isChecked() is True


def test_apply_defect_from_dialog_emits_set_defect_command():
    item = Valve_4_2_Ways(domain="hydraulic")
    item.properties["k"] = 1e-7
    dialog = item.build_defect_dialog()
    dialog._field_k.setText("3.3e-8")
    dialog._field_stuck.setChecked(True)

    received = []
    item.command.connect(lambda node_id, payload: received.append((node_id, payload)))
    item.apply_defect_from_dialog(dialog)

    assert len(received) == 1
    node_id, payload = received[0]
    assert node_id == item.id
    assert payload == {"action": "set_defect", "k": 3.3e-8, "stuck": True}


def test_apply_defect_from_dialog_emits_clear_defect_when_restore_requested():
    item = Valve_4_2_Ways(domain="hydraulic")
    item.properties["k"] = 1e-7
    dialog = item.build_defect_dialog()
    dialog.restore_requested = True

    received = []
    item.command.connect(lambda node_id, payload: received.append((node_id, payload)))
    item.apply_defect_from_dialog(dialog)

    assert received == [(item.id, {"action": "clear_defect"})]


def test_build_defect_dialog_k_field_rejects_zero():
    item = Valve_4_2_Ways(domain="hydraulic")
    item.properties["k"] = 1e-7
    dialog = item.build_defect_dialog()
    dialog._field_k.setText("0")
    dialog._refresh_ok_button()
    assert dialog._ok_btn.isEnabled() is False


def test_build_defect_dialog_k_field_rejects_negative():
    item = Valve_4_2_Ways(domain="hydraulic")
    item.properties["k"] = 1e-7
    dialog = item.build_defect_dialog()
    dialog._field_k.setText("-3")
    dialog._refresh_ok_button()
    assert dialog._ok_btn.isEnabled() is False


def test_build_defect_dialog_k_field_accepts_small_positive():
    item = Valve_4_2_Ways(domain="hydraulic")
    item.properties["k"] = 1e-7
    dialog = item.build_defect_dialog()
    dialog._field_k.setText("0.001")
    dialog._refresh_ok_button()
    assert dialog._ok_btn.isEnabled() is True


# ---------------------------------------------------------------------------
# Finding 2 -- canal de comando real: item gráfico -> nó de domínio real,
# sem SimulationController, no mesmo padrão dos testes de engine hidráulico.
# ---------------------------------------------------------------------------

def test_apply_defect_from_dialog_drives_real_domain_node_via_command_channel():
    from simulation.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways as DomainValve_4_2_Ways

    item = Valve_4_2_Ways(domain="hydraulic")
    item.properties["k"] = 1e-7

    domain_node = DomainValve_4_2_Ways("v42", domain="hydraulic", properties={"k": 1e-7})
    for port in ("P", "A", "B", "R"):
        domain_node.add_anchor(port, domain="hydraulic")

    # item.command emite (node_id, payload); handle_command só recebe o
    # payload -- mesmo "roteamento por id" que SimulationController.command
    # faz em produção (simulation/simulation_session.py), só que aqui já
    # sabemos que é o único nó, então despachamos direto.
    item.command.connect(lambda node_id, payload: domain_node.handle_command(payload))

    dialog = item.build_defect_dialog()
    dialog._field_k.setText("3.3e-8")
    dialog._field_stuck.setChecked(True)

    item.apply_defect_from_dialog(dialog)

    assert domain_node.defect_active is True
    assert domain_node.k == 3.3e-8

    item.update_from_domain(domain_node)
    assert item._defect_indicator is True
