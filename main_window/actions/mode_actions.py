from PyQt6.QtGui import QAction, QActionGroup
from editor.mode import EditorMode

def create_mode_actions(main_window):
    actions = {}

    group = QActionGroup(main_window)
    group.setExclusive(True)
    main_window.mode_group = group

    actions["mode_select"] = QAction("Select", main_window)
    actions["mode_select"].setCheckable(True)
    actions["mode_select"].setData(EditorMode.SELECT)
    actions["mode_select"].toggled.connect(lambda checked: checked and main_window.set_mode(EditorMode.SELECT))
    group.addAction(actions["mode_select"])

    actions["mode_connect"] = QAction("Connect", main_window)
    actions["mode_connect"].setCheckable(True)
    actions["mode_connect"].setData(EditorMode.CONNECT)
    actions["mode_connect"].toggled.connect(lambda checked: checked and main_window.set_mode(EditorMode.CONNECT))
    group.addAction(actions["mode_connect"])

    actions["mode_simulate"] = QAction("Simulate", main_window)
    actions["mode_simulate"].setCheckable(True)
    actions["mode_simulate"].setData(EditorMode.SIMULATE)
    actions["mode_simulate"].setShortcut("Ctrl+G")
    actions["mode_simulate"].toggled.connect(lambda checked: checked and main_window.set_mode(EditorMode.SIMULATE if checked else EditorMode.SELECT))
    group.addAction(actions["mode_simulate"])

    return actions