"""Tests for the Contact's "Button" actuator option (merge of the former
ButtonSwitch into Contact: same body sprites, button drawn as an overlay
instead of a duplicated sprite set)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QMenu
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtCore import QPointF, Qt

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.switch.contact import (
    Contact,
    BUTTON_SENSOR,
    BUTTON_OVERLAY_OFFSETS,
)
from simulation.nodes.switch.contact import Contact as ContactNode


def _combo_items(combo):
    return [combo.itemText(i) for i in range(combo.count())]


def _render(item):
    # Premultiplied: QPainter's SourceOver compositing is defined exactly
    # for this format, so drawing the base sprite then the overlay in two
    # separate drawPixmap() calls doesn't leave sub-1%-alpha rounding dust.
    image = QImage(item.width, item.height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    item.paint(painter, None)
    painter.end()
    return image


def _images_equal(a: QImage, b: QImage) -> bool:
    # QImage.__eq__ can report False on byte-buffer/metadata differences
    # (e.g. bytesPerLine padding) even when every pixel matches, so compare
    # pixel-by-pixel instead of relying on it.
    a = a.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    b = b.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    if a.size() != b.size():
        return False
    return all(
        a.pixel(x, y) == b.pixel(x, y)
        for x in range(a.width())
        for y in range(a.height())
    )


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


# --------------------------
# Domain: handle_command
# --------------------------

def test_handle_command_sets_state():
    node = ContactNode("c1", domain="electric")
    node.handle_command({"type": "switch", "value": 1})
    assert node.state == 1
    node.handle_command({"type": "switch", "value": 0})
    assert node.state == 0


def test_handle_command_ignores_other_command_types():
    node = ContactNode("c1", domain="electric")
    node.state = 1
    node.handle_command({"type": "other", "value": 0})
    assert node.state == 1


def test_handle_command_ignores_invalid_values():
    node = ContactNode("c1", domain="electric")
    node.state = 1
    node.handle_command({"type": "switch", "value": 5})
    assert node.state == 1


# --------------------------
# Dialog: "Button" as an option in the actuator combo
# --------------------------

def test_dialog_lists_button_option():
    node = Contact(domain="electric")
    dialog = node.build_properties_dialog()
    assert "Button" in _combo_items(dialog._combo_relay)


def test_selecting_button_in_dialog_sets_sentinel():
    node = Contact(domain="electric")
    dialog = node.build_properties_dialog()
    dialog._combo_relay.setCurrentText("Button")
    node.apply_properties_from_dialog(dialog)
    assert node.properties["actuator_sensor"] == BUTTON_SENSOR


def test_dialog_preselects_button_when_already_set():
    node = Contact(domain="electric")
    node.set_actuator_sensor(BUTTON_SENSOR)
    dialog = node.build_properties_dialog()
    assert dialog._combo_relay.currentText() == "Button"


# --------------------------
# set_actuator_sensor: the sentinel never leaks into the visible label
# --------------------------

def test_button_sensor_leaves_label_empty():
    node = Contact(domain="electric")
    node.set_actuator_sensor(BUTTON_SENSOR)
    label = node.labels.get("actuator_sensor_name")
    assert label.properties["text"] == ""


# --------------------------
# Context menu
# --------------------------

def test_context_menu_offers_button_option():
    node = Contact(domain="electric")
    menu = QMenu()
    node.extend_context_menu(menu)
    labels = [a.text() for a in menu.actions()]
    assert "Button" in labels


# "Button" is a submenu with latch/momentary options, not a flat checkable
# action -- see tests/test_contact_button_mode.py for that behavior.


# --------------------------
# Overlay compositing
# --------------------------

def test_button_overlay_offsets_locked():
    # Found by exhaustive pixel search against the (now-retired)
    # button_switch_*.png sprites (SSE == 0 at these offsets) -- locked in
    # so a future sprite swap doesn't silently drift.
    assert BUTTON_OVERLAY_OFFSETS == {
        ("NO", 0): QPointF(2, 25),
        ("NO", 1): QPointF(21, 25),
        ("NC", 0): QPointF(7, 25),
        ("NC", 1): QPointF(22, 25),
    }


def test_button_overlay_changes_rendered_pixels():
    # Confirms the overlay actually gets composited on top of the bare
    # contact body (not just that BUTTON_OVERLAY_OFFSETS is populated).
    bare = Contact(domain="electric")
    bare.set_contact_type("NO")
    bare.body_state = 1
    bare.update_body_visuals()

    with_button = Contact(domain="electric")
    with_button.set_contact_type("NO")
    with_button.set_actuator_sensor(BUTTON_SENSOR)
    with_button.body_state = 1
    with_button.update_body_visuals()

    assert not _images_equal(_render(bare), _render(with_button))


def test_no_overlay_drawn_when_sensor_is_not_button():
    item = Contact(domain="electric")
    item.set_contact_type("NO")
    item.body_state = 1
    item.update_body_visuals()

    rendered = _render(item)
    target = QPixmap("resources/nodes/contact/contact_no_closed.png").toImage()
    assert _images_equal(rendered, target)


# --------------------------
# End-to-end: click drives the domain node when "Button" is selected
# --------------------------

def test_click_on_button_contact_toggles_domain_state_end_to_end():
    item = Contact(domain="electric")
    item.set_actuator_sensor(BUTTON_SENSOR)
    item.set_button_mode("latch")  # toggle-on-click behavior; momentary is now the default
    item.simulation_mode = True

    domain_node = ContactNode("c1", domain="electric", properties={"actuator_sensor": BUTTON_SENSOR})
    item.command.connect(lambda node_id, payload: domain_node.handle_command(payload))

    item.mousePressEvent(FakeMouseEvent())
    assert domain_node.state == 1
    item.update_from_domain(domain_node)  # a real simulation tick would sync this back

    item.mousePressEvent(FakeMouseEvent())
    assert domain_node.state == 0
