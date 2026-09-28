"""DefectMixin: generic set/clear/snapshot/restore of declared defect fields."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.nodes.defect import DefectMixin
from simulation.nodes.nodes import Node


class _FakeNode(DefectMixin, Node):
    DEFECT_FIELDS = {
        "k": "k",
        "stuck": "stuck_defect",
        "mode": "mode",
        "n": "n",
        "ghost": "ghost_attr",  # never defined on the instance
    }

    def __init__(self, node_id="n1", **kwargs):
        super().__init__(node_id, "fake", **kwargs)
        self.k = 1.0
        self.stuck_defect = False
        self.mode = "none"
        self.n = 3
        self.changed_calls = 0
        self.passed_commands = []

    def _on_defect_changed(self):
        self.changed_calls += 1


class _RecordingBase(Node):
    def handle_command(self, command):
        self.passed_commands.append(command)


class _FakeNodeWithBase(DefectMixin, _RecordingBase):
    DEFECT_FIELDS = {"k": "k"}

    def __init__(self):
        super().__init__("n2", "fake")
        self.k = 1.0
        self.passed_commands = []


def test_fresh_node_has_no_active_defect():
    node = _FakeNode()
    assert node.defect_active is False
    assert node.defect_note == ""


def test_set_defect_changes_attributes_and_marks_active():
    node = _FakeNode()
    node.handle_command({"action": "set_defect", "k": 0.5, "stuck": True})
    assert node.k == 0.5
    assert node.stuck_defect is True
    assert node.defect_active is True


def test_partial_set_defect_keeps_other_fields():
    node = _FakeNode()
    node.handle_command({"action": "set_defect", "k": 0.5})
    node.handle_command({"action": "set_defect", "stuck": True})
    assert node.k == 0.5
    assert node.stuck_defect is True


def test_repeated_set_keeps_first_snapshot_so_clear_restores_healthy_value():
    node = _FakeNode()
    node.handle_command({"action": "set_defect", "k": 0.5})
    node.handle_command({"action": "set_defect", "k": 0.2})
    node.handle_command({"action": "clear_defect"})
    assert node.k == 1.0
    assert node.defect_active is False


def test_clear_defect_restores_every_field():
    node = _FakeNode()
    node.handle_command({"action": "set_defect", "k": 0.5, "stuck": True, "mode": "welded", "n": 7})
    node.handle_command({"action": "clear_defect"})
    assert (node.k, node.stuck_defect, node.mode, node.n) == (1.0, False, "none", 3)
    assert node.defect_active is False


def test_unknown_key_and_missing_attribute_are_ignored():
    node = _FakeNode()
    node.handle_command({"action": "set_defect", "bogus": 1, "ghost": 5})
    assert not hasattr(node, "ghost_attr")
    assert not hasattr(node, "bogus")
    assert node.defect_active is False


def test_values_are_coerced_to_the_original_type():
    node = _FakeNode()
    node.handle_command({"action": "set_defect", "k": "0.25", "stuck": 1, "mode": 42, "n": 5.0})
    assert node.k == 0.25 and isinstance(node.k, float)
    assert node.stuck_defect is True
    assert node.mode == "42"
    assert node.n == 5 and isinstance(node.n, int)


def test_setting_value_back_to_original_reads_inactive():
    node = _FakeNode()
    node.handle_command({"action": "set_defect", "stuck": True})
    node.handle_command({"action": "set_defect", "stuck": False})
    assert node.defect_active is False


def test_defect_value_reads_mapped_attribute():
    node = _FakeNode()
    node.handle_command({"action": "set_defect", "stuck": True})
    assert node.defect_value("stuck") is True
    assert node.defect_value("k") == 1.0
    assert node.defect_value("bogus") is None
    assert node.defect_value("ghost") is None


def test_note_is_stored_on_set_and_on_clear():
    node = _FakeNode()
    node.handle_command({"action": "set_defect", "k": 0.5, "note": "debris"})
    assert node.defect_note == "debris"
    node.handle_command({"action": "clear_defect", "note": "fixed"})
    assert node.defect_note == "fixed"
    node.handle_command({"action": "set_defect", "k": 0.5})
    assert node.defect_note == ""


def test_on_defect_changed_called_on_set_and_clear():
    node = _FakeNode()
    node.handle_command({"action": "set_defect", "k": 0.5})
    node.handle_command({"action": "clear_defect"})
    assert node.changed_calls == 2


def test_handle_defect_command_reports_whether_it_consumed_the_command():
    node = _FakeNode()
    assert node.handle_defect_command({"action": "set_defect", "k": 0.5}) is True
    assert node.handle_defect_command({"action": "clear_defect"}) is True
    assert node.handle_defect_command({"type": "actuator", "side": "left", "value": 1}) is False


def test_non_defect_commands_reach_the_next_class_in_the_mro():
    node = _FakeNodeWithBase()
    node.handle_command({"type": "switch", "value": 1})
    node.handle_command({"action": "set_defect", "k": 0.5})
    assert node.passed_commands == [{"type": "switch", "value": 1}]
    assert node.k == 0.5
