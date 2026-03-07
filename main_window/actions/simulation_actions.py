from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QDoubleSpinBox, QLabel, QWidget, QHBoxLayout

SPEED_STEPS = [1, 2, 4, 8]

def create_simulation_actions(main_window):
    actions = {}

    actions["run"] = QAction("Run", main_window)
    actions["run"].setShortcut("Space")
    actions["run"].setEnabled(False)
    actions["run"].triggered.connect(main_window.toggle_play)

    actions["step_back"] = QAction("Step Back", main_window)
    actions["step_back"].setShortcut("Ctrl+Z")
    actions["step_back"].setEnabled(False)
    actions["step_back"].triggered.connect(main_window.on_step_back)

    actions["step_forward"] = QAction("Step Forward", main_window)
    actions["step_forward"].setShortcut("Ctrl+Y")
    actions["step_forward"].setEnabled(False)
    actions["step_forward"].triggered.connect(main_window.on_step_forward)

    actions["dt"] = QAction("dt: 0.100s", main_window)
    actions["dt"].triggered.connect(main_window.on_dt_clicked)

    actions["speed"] = QAction("1x", main_window)
    actions["speed"].triggered.connect(main_window.on_cycle_speed)

    return actions
