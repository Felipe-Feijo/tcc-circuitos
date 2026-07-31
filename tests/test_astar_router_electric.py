import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_generator.astar_router import SPRITE_SIZES, get_exit_dir
from circuit_generator.sprite_metrics import METRICS


def test_sprite_sizes_registered_for_electric_types():
    assert SPRITE_SIZES["RelaySwitch"] == (METRICS.relay_switch_width, METRICS.relay_switch_height)
    assert SPRITE_SIZES["SolenoidCoil"] == (METRICS.solenoid_coil_width, METRICS.solenoid_coil_height)
    assert SPRITE_SIZES["ButtonSwitch"] == (METRICS.button_switch_width, METRICS.button_switch_height)
    assert SPRITE_SIZES["VoltageSource"] == (METRICS.vsource_pix_w, METRICS.vsource_pix_h)
    assert SPRITE_SIZES["Ground"] == (METRICS.ground_pix_w, METRICS.ground_pix_h)


def test_relay_switch_exit_directions():
    assert get_exit_dir("RelaySwitch", "T") == "UP"
    assert get_exit_dir("RelaySwitch", "B") == "DOWN"


def test_solenoid_coil_exit_directions():
    assert get_exit_dir("SolenoidCoil", "T") == "UP"
    assert get_exit_dir("SolenoidCoil", "B") == "DOWN"


def test_button_switch_exit_directions():
    assert get_exit_dir("ButtonSwitch", "T") == "UP"
    assert get_exit_dir("ButtonSwitch", "B") == "DOWN"


def test_voltage_source_dynamic_anchor_exits_down():
    # VoltageSource fica no TOPO da faixa elétrica -- os fios descem dela
    # pros degraus abaixo, então a saída aponta pra BAIXO (mesmo raciocínio
    # inverso do PressureLine, que aponta sempre UP).
    assert get_exit_dir("VoltageSource", "X1") == "DOWN"
    assert get_exit_dir("VoltageSource", "X17") == "DOWN"


def test_ground_dynamic_anchor_exits_up():
    # Ground fica na BASE da faixa elétrica -- os fios entram nela vindos de
    # cima (das bobinas), então a saída aponta pra CIMA.
    assert get_exit_dir("Ground", "X1") == "UP"
    assert get_exit_dir("Ground", "X9") == "UP"


def test_relay_coil_sprite_size_registered():
    assert SPRITE_SIZES["RelayCoil"] == (METRICS.relay_coil_width, METRICS.relay_coil_height)


def test_relay_coil_exit_directions():
    assert get_exit_dir("RelayCoil", "T") == "UP"
    assert get_exit_dir("RelayCoil", "B") == "DOWN"
