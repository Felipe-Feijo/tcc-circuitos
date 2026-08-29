import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.sprite_metrics import METRICS


def test_contact_dimensions():
    assert METRICS.contact_width == 50
    assert METRICS.contact_height == 75


def test_solenoid_coil_dimensions():
    assert METRICS.solenoid_coil_width == 50
    assert METRICS.solenoid_coil_height == 50


def test_voltage_source_and_ground_terminal_dimensions():
    assert METRICS.vsource_pix_w == 70
    assert METRICS.vsource_pix_h == 100
    assert METRICS.ground_pix_w == 60
    assert METRICS.ground_pix_h == 75


def test_contact_anchor_local():
    anchors = METRICS.anchor_local["Contact"]
    assert anchors["T"] == (50 * 39 / 50, 0)
    assert anchors["B"] == (50 * 39 / 50, 75)


def test_solenoid_coil_anchor_local_is_hardcoded_center():
    anchors = METRICS.anchor_local["SolenoidCoil"]
    assert anchors["T"] == (25.0, 0.0)   # width/2, top
    assert anchors["B"] == (25.0, 50.0)  # width/2, bottom


def test_relay_coil_dimensions():
    assert METRICS.relay_coil_width == 50
    assert METRICS.relay_coil_height == 50


def test_relay_coil_anchor_local_is_hardcoded_center():
    anchors = METRICS.anchor_local["RelayCoil"]
    assert anchors["T"] == (25.0, 0.0)   # width/2, top
    assert anchors["B"] == (25.0, 50.0)  # width/2, bottom
