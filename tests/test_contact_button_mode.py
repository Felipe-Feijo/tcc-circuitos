"""Tests for the Contact's "Button" actuator latch/momentary mode."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QMenu
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.switch.contact import Contact, BUTTON_SENSOR
from graphics.items.base.diagram_item_base import DiagramItemBase


class FakeMouseEvent:
    def __init__(self, button=Qt.MouseButton.LeftButton):
        self._button = button
        self.accepted = False

    def button(self):
        return self._button

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.accepted = False


def _combo_items(combo):
    return [combo.itemText(i) for i in range(combo.count())]


# --------------------------
# Sprites: mode-aware overlay
# --------------------------

def test_button_overlay_uses_momentary_sprites_by_default():
    item = Contact(domain="electric")
    item.set_actuator_sensor(BUTTON_SENSOR)
    item.body_state = 1

    pixmap, _ = item._button_overlay()
    expected = QPixmap("resources/actuators/contact_button/contact_button_active.png")
    assert pixmap.toImage() == expected.toImage()


def test_button_overlay_uses_latch_sprites_when_set():
    item = Contact(domain="electric")
    item.set_actuator_sensor(BUTTON_SENSOR)
    item.set_button_mode("latch")
    item.body_state = 1

    pixmap, _ = item._button_overlay()
    expected = QPixmap("resources/actuators/contact_button/contact_button_latch_active.png")
    assert pixmap.toImage() == expected.toImage()


def test_button_overlay_inactive_sprites_track_mode_too():
    item = Contact(domain="electric")
    item.set_actuator_sensor(BUTTON_SENSOR)
    item.set_button_mode("momentary")
    item.body_state = 0

    pixmap, _ = item._button_overlay()
    expected = QPixmap("resources/actuators/contact_button/contact_button_inactive.png")
    assert pixmap.toImage() == expected.toImage()


# --------------------------
# Mouse press/release
# --------------------------

def test_mouse_press_toggles_bit_for_latch_button():
    item = Contact(domain="electric")
    item.set_actuator_sensor(BUTTON_SENSOR)
    item.set_button_mode("latch")
    item.simulation_mode = True
    item.body_state = 0

    received = []
    item.command.connect(lambda node_id, payload: received.append(payload))

    item.mousePressEvent(FakeMouseEvent())

    assert received == [{"type": "switch", "value": 1}]


def test_mouse_press_sets_momentary_button_active():
    item = Contact(domain="electric")
    item.set_actuator_sensor(BUTTON_SENSOR)
    item.set_button_mode("momentary")
    item.simulation_mode = True
    item.body_state = 0

    received = []
    item.command.connect(lambda node_id, payload: received.append(payload))

    item.mousePressEvent(FakeMouseEvent())

    assert received == [{"type": "switch", "value": 1}]


def test_mouse_release_deactivates_momentary_button():
    item = Contact(domain="electric")
    item.set_actuator_sensor(BUTTON_SENSOR)
    item.set_button_mode("momentary")
    item.simulation_mode = True
    item.body_state = 0

    received = []
    item.command.connect(lambda node_id, payload: received.append(payload))

    item.mousePressEvent(FakeMouseEvent())
    item.mouseReleaseEvent(FakeMouseEvent())

    assert received == [
        {"type": "switch", "value": 1},
        {"type": "switch", "value": 0},
    ]


def test_mouse_release_without_prior_momentary_press_emits_nothing():
    item = Contact(domain="electric")
    item.set_actuator_sensor(BUTTON_SENSOR)
    item.set_button_mode("momentary")
    item.simulation_mode = True

    received = []
    item.command.connect(lambda node_id, payload: received.append(payload))

    with patch.object(DiagramItemBase, 'mouseReleaseEvent', lambda self, event: None):
        item.mouseReleaseEvent(FakeMouseEvent())

    assert received == []


def test_mouse_release_does_not_fire_for_latch_button():
    # A latch click already sent its command on press -- release must be a
    # no-op (falls through to the base class), not a second command.
    item = Contact(domain="electric")
    item.set_actuator_sensor(BUTTON_SENSOR)
    item.set_button_mode("latch")
    item.simulation_mode = True

    received = []
    item.command.connect(lambda node_id, payload: received.append(payload))

    item.mousePressEvent(FakeMouseEvent())
    with patch.object(DiagramItemBase, 'mouseReleaseEvent', lambda self, event: None):
        item.mouseReleaseEvent(FakeMouseEvent())

    assert received == [{"type": "switch", "value": 1}]


# --------------------------
# Context menu: Button is a submenu with latch/momentary options
# --------------------------

def test_actuator_menu_button_is_submenu_with_latch_and_momentary_options():
    item = Contact(domain="electric")
    menu = QMenu()
    item.extend_context_menu(menu)

    button_entries = [a for a in menu.actions() if a.text() == "Button"]
    assert len(button_entries) == 1
    assert button_entries[0].menu() is not None

    submenu_labels = [a.text() for a in button_entries[0].menu().actions()]
    assert submenu_labels == ["Retido", "Momentâneo"]


def test_actuator_menu_button_latch_checked_when_current_mode_latch():
    item = Contact(domain="electric")
    item.set_actuator_sensor(BUTTON_SENSOR)
    item.set_button_mode("latch")
    menu = QMenu()
    item.extend_context_menu(menu)

    button_menu = next(a for a in menu.actions() if a.text() == "Button").menu()
    checked = {a.text(): a.isChecked() for a in button_menu.actions()}
    assert checked == {"Retido": True, "Momentâneo": False}


def test_actuator_menu_button_defaults_to_momentary_checked():
    item = Contact(domain="electric")
    item.set_actuator_sensor(BUTTON_SENSOR)
    menu = QMenu()
    item.extend_context_menu(menu)

    button_menu = next(a for a in menu.actions() if a.text() == "Button").menu()
    checked = {a.text(): a.isChecked() for a in button_menu.actions()}
    assert checked == {"Retido": False, "Momentâneo": True}


def test_actuator_menu_button_momentary_checked_when_current_mode_momentary():
    item = Contact(domain="electric")
    item.set_actuator_sensor(BUTTON_SENSOR)
    item.set_button_mode("momentary")
    menu = QMenu()
    item.extend_context_menu(menu)

    button_menu = next(a for a in menu.actions() if a.text() == "Button").menu()
    checked = {a.text(): a.isChecked() for a in button_menu.actions()}
    assert checked == {"Retido": False, "Momentâneo": True}


def test_actuator_menu_selecting_momentary_sets_sensor_and_mode():
    item = Contact(domain="electric")
    menu = QMenu()
    item.extend_context_menu(menu)

    button_menu = next(a for a in menu.actions() if a.text() == "Button").menu()
    momentary_action = next(a for a in button_menu.actions() if a.text() == "Momentâneo")
    momentary_action.trigger()

    assert item.properties["actuator_sensor"] == BUTTON_SENSOR
    assert item.properties["button_mode"] == "momentary"


# --------------------------
# Properties dialog: "Trava" checkbox tied to the Button selection
# (momentary is the default; the checkbox opts INTO latch)
# --------------------------

def test_properties_dialog_latch_checkbox_reflects_current_mode():
    item = Contact(domain="electric")
    item.set_actuator_sensor(BUTTON_SENSOR)
    item.set_button_mode("latch")

    dialog = item.build_properties_dialog()

    assert dialog._field_latch.isChecked() is True


def test_apply_properties_from_dialog_button_latch_checked():
    item = Contact(domain="electric")

    dialog = item.build_properties_dialog()
    dialog._combo_relay.setCurrentText("Button")
    dialog._field_latch.setChecked(True)
    item.apply_properties_from_dialog(dialog)

    assert item.properties["actuator_sensor"] == BUTTON_SENSOR
    assert item.properties["button_mode"] == "latch"


def test_apply_properties_from_dialog_button_latch_unchecked_is_momentary():
    item = Contact(domain="electric")
    item.set_actuator_sensor(BUTTON_SENSOR)
    item.set_button_mode("latch")

    dialog = item.build_properties_dialog()
    dialog._combo_relay.setCurrentText("Button")
    dialog._field_latch.setChecked(False)
    item.apply_properties_from_dialog(dialog)

    assert item.properties["button_mode"] == "momentary"
