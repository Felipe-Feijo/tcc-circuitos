"""Regression test: main_window.on_change_font_size() calls
LabelItem.refresh_default_font_size() directly on every label in the
scene, with no notion of any particular node's own positioning logic.
DirectionalValveItem's actuator label (YA1/YA0/... over the solenoid/
limit-switch sprite) and CoilItem's sensor-name label both position
themselves off the label's OWN rendered bounding rect -- a font-size
change resizes that rect, so without label.on_reposition wired up,
their position goes stale (grows away from its intended spot instead of
staying centered/anchored there)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from graphics.items.base.nodes.directional_valve.valve_5_2_ways import Valve_5_2_Ways
from graphics.items.base.nodes.coil.relay_coil import RelayCoil


def _bigger_font():
    f = app.font()
    f.setPointSize(f.pointSize() + 12)
    return f


def test_left_actuator_label_stays_centered_after_font_size_change():
    """Left actuator: the valve body sits to ITS RIGHT, so a plain
    top-left anchor would grow the label into the body as it gets
    bigger -- it must recenter on font-size change instead."""
    item = Valve_5_2_Ways(domain="pneumatic")
    item.set_actuator("left", "solenoid", "YA1")
    label = item.special_labels["actuator_label_left"]

    old_font = app.font()
    app.setFont(_bigger_font())
    try:
        label.refresh_default_font_size()
    finally:
        app.setFont(old_font)

    rect = item.actuator_rects["left"]
    expected_center_x = rect.x() + rect.width() * 0.42
    lbl_rect = label.boundingRect()
    actual_center_x = label.pos().x() - item.visual_offset.x() + lbl_rect.width() / 2
    assert abs(actual_center_x - expected_center_x) < 0.5


def test_right_actuator_label_keeps_static_top_left_anchor():
    """Right actuator: the valve body sits to ITS LEFT, so growing
    rightward from a fixed top-left anchor (the original, static
    ratio-based formula) already grows AWAY from the body at any font
    size -- must NOT be recentered (that would grow the label back
    toward/over the body, as it did before this fix)."""
    item = Valve_5_2_Ways(domain="pneumatic")
    item.set_actuator("right", "solenoid", "YA0")
    label = item.special_labels["actuator_label_right"]

    rect = item.actuator_rects["right"]
    expected_x = rect.x() + rect.width() * 0.18

    old_font = app.font()
    app.setFont(_bigger_font())
    try:
        label.refresh_default_font_size()
    finally:
        app.setFont(old_font)

    actual_x = label.pos().x() - item.visual_offset.x()
    assert abs(actual_x - expected_x) < 0.5


def test_coil_sensor_label_stays_right_anchored_after_font_size_change():
    item = RelayCoil(domain="electric")
    label = item.special_labels["sensor_name"]
    label.set_text("K1")

    old_font = app.font()
    app.setFont(_bigger_font())
    try:
        label.refresh_default_font_size()
    finally:
        app.setFont(old_font)

    lbl_rect = label.boundingRect()
    expected_x = -lbl_rect.width() - item.LABEL_GAP
    assert abs(label.pos().x() - expected_x) < 0.5
