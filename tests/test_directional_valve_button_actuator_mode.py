"""Tests for the button actuator's latch/momentary mode."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QMenu
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QPointF, Qt

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.directional_valve.valve_4_2_ways import Valve_4_2_Ways
from graphics.items.base.diagram_item_base import DiagramItemBase


class FakeMouseEvent:
    """Minimal stand-in for QGraphicsSceneMouseEvent (PyQt6 doesn't allow
    instantiating it directly) -- just enough for mousePress/ReleaseEvent."""

    def __init__(self, x: float, y: float, button=Qt.MouseButton.LeftButton):
        self._pos = QPointF(x, y)
        self._button = button
        self.accepted = False

    def pos(self) -> QPointF:
        return self._pos

    def button(self):
        return self._button

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.accepted = False


def _press_at_actuator(item, side):
    rect = item.actuator_rects[side].translated(item.visual_offset)
    center = rect.center()
    return FakeMouseEvent(center.x(), center.y())


def test_set_actuator_button_defaults_to_momentary_mode():
    item = Valve_4_2_Ways(domain="pneumatic")
    item.set_actuator("left", "button")
    assert item.properties["actuators"]["left"] == {"type": "button", "mode": "momentary"}


def test_set_actuator_button_with_latch_mode():
    item = Valve_4_2_Ways(domain="pneumatic")
    item.set_actuator("left", "button", mode="latch")
    assert item.properties["actuators"]["left"] == {"type": "button", "mode": "latch"}


def test_button_actuator_latch_mode_loads_latch_sprites():
    item = Valve_4_2_Ways(domain="pneumatic")
    item.set_actuator("left", "button", mode="latch")

    expected_active = QPixmap("resources/actuators/button/button_latch_active.png")
    expected_inactive = QPixmap("resources/actuators/button/button_latch_inactive.png")

    visuals = item.actuator_visuals["left"]
    assert visuals["active"].toImage() == expected_active.toImage()
    assert visuals["inactive"].toImage() == expected_inactive.toImage()


def test_button_actuator_momentary_mode_loads_plain_sprites():
    item = Valve_4_2_Ways(domain="pneumatic")
    item.set_actuator("left", "button", mode="momentary")

    expected_active = QPixmap("resources/actuators/button/button_active.png")
    expected_inactive = QPixmap("resources/actuators/button/button_inactive.png")

    visuals = item.actuator_visuals["left"]
    assert visuals["active"].toImage() == expected_active.toImage()
    assert visuals["inactive"].toImage() == expected_inactive.toImage()


def test_mouse_press_toggles_bit_for_latch_button():
    item = Valve_4_2_Ways(domain="pneumatic")
    item.set_actuator("left", "button", mode="latch")
    item.simulation_mode = True
    item.bits["left"] = 0

    received = []
    item.command.connect(lambda node_id, payload: received.append(payload))

    item.mousePressEvent(_press_at_actuator(item, "left"))

    assert received == [{"type": "actuator", "value": 1, "side": "left"}]


def test_mouse_press_sets_momentary_button_active():
    item = Valve_4_2_Ways(domain="pneumatic")
    item.set_actuator("left", "button", mode="momentary")
    item.simulation_mode = True
    item.bits["left"] = 0

    received = []
    item.command.connect(lambda node_id, payload: received.append(payload))

    item.mousePressEvent(_press_at_actuator(item, "left"))

    assert received == [{"type": "actuator", "value": 1, "side": "left"}]


def test_mouse_release_deactivates_momentary_button():
    item = Valve_4_2_Ways(domain="pneumatic")
    item.set_actuator("left", "button", mode="momentary")
    item.simulation_mode = True
    item.bits["left"] = 0

    received = []
    item.command.connect(lambda node_id, payload: received.append(payload))

    item.mousePressEvent(_press_at_actuator(item, "left"))
    item.mouseReleaseEvent(FakeMouseEvent(0, 0))

    assert received == [
        {"type": "actuator", "value": 1, "side": "left"},
        {"type": "actuator", "value": 0, "side": "left"},
    ]


def test_mouse_release_without_prior_momentary_press_emits_nothing():
    item = Valve_4_2_Ways(domain="pneumatic")
    item.set_actuator("left", "button", mode="momentary")
    item.simulation_mode = True

    received = []
    item.command.connect(lambda node_id, payload: received.append(payload))

    with patch.object(DiagramItemBase, 'mouseReleaseEvent', lambda self, event: None):
        item.mouseReleaseEvent(FakeMouseEvent(0, 0))

    assert received == []


# --------------------------
# Context menu: Button is a submenu with latch/momentary options
# --------------------------

def test_actuator_menu_button_is_submenu_not_flat_action():
    item = Valve_4_2_Ways(domain="pneumatic")
    menu = QMenu()
    item._populate_actuator_menu(menu, side="left")

    button_entries = [a for a in menu.actions() if a.text() == "Button"]
    assert len(button_entries) == 1
    assert button_entries[0].menu() is not None

    submenu_labels = [a.text() for a in button_entries[0].menu().actions()]
    assert submenu_labels == ["Latched", "Momentary"]


def test_actuator_menu_button_latch_checked_when_current_mode_latch():
    item = Valve_4_2_Ways(domain="pneumatic")
    item.set_actuator("left", "button", mode="latch")
    menu = QMenu()
    item._populate_actuator_menu(menu, side="left")

    button_menu = next(a for a in menu.actions() if a.text() == "Button").menu()
    checked = {a.text(): a.isChecked() for a in button_menu.actions()}
    assert checked == {"Latched": True, "Momentary": False}


def test_actuator_menu_button_momentary_checked_when_current_mode_momentary():
    item = Valve_4_2_Ways(domain="pneumatic")
    item.set_actuator("left", "button", mode="momentary")
    menu = QMenu()
    item._populate_actuator_menu(menu, side="left")

    button_menu = next(a for a in menu.actions() if a.text() == "Button").menu()
    checked = {a.text(): a.isChecked() for a in button_menu.actions()}
    assert checked == {"Latched": False, "Momentary": True}


def test_actuator_menu_selecting_momentary_sets_actuator_momentary_mode():
    item = Valve_4_2_Ways(domain="pneumatic")
    item.set_actuator("left", "button", mode="latch")
    menu = QMenu()
    item._populate_actuator_menu(menu, side="left")

    button_menu = next(a for a in menu.actions() if a.text() == "Button").menu()
    momentary_action = next(a for a in button_menu.actions() if a.text() == "Momentary")
    momentary_action.trigger()

    assert item.properties["actuators"]["left"] == {"type": "button", "mode": "momentary"}


# --------------------------
# Properties dialog: "Trava" checkbox tied to the Button selection
# (momentary is the default; the checkbox opts INTO latch)
# --------------------------

def test_properties_dialog_latch_checkbox_reflects_current_mode():
    item = Valve_4_2_Ways(domain="pneumatic")
    item.set_actuator("left", "button", mode="momentary")
    item.set_actuator("right", "button", mode="latch")

    dialog = item.build_properties_dialog()

    assert dialog._field_latch_left.isChecked() is False
    assert dialog._field_latch_right.isChecked() is True


def test_apply_properties_from_dialog_button_latch_checked():
    item = Valve_4_2_Ways(domain="pneumatic")
    item.set_actuator("left", "button", mode="momentary")

    dialog = item.build_properties_dialog()
    dialog._field_latch_left.setChecked(True)
    item.apply_properties_from_dialog(dialog)

    assert item.properties["actuators"]["left"] == {"type": "button", "mode": "latch"}


def test_apply_properties_from_dialog_button_latch_unchecked():
    item = Valve_4_2_Ways(domain="pneumatic")
    item.set_actuator("left", "button", mode="latch")

    dialog = item.build_properties_dialog()
    dialog._field_latch_left.setChecked(False)
    item.apply_properties_from_dialog(dialog)

    assert item.properties["actuators"]["left"] == {"type": "button", "mode": "momentary"}
