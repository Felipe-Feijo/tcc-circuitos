from PyQt6.QtGui import QAction


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

    return actions