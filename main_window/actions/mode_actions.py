from PyQt6.QtGui import QAction, QActionGroup

def create_mode_actions(main_window):
    actions = {}

    group = QActionGroup(main_window)
    group.setExclusive(True)
    main_window.mode_group = group

    actions["mode_select"] = QAction("Select", main_window)
    actions["mode_select"].setCheckable(True)
    actions["mode_select"].setData(None)
    actions["mode_select"].toggled.connect(lambda checked: checked and main_window.set_mode(None))
    group.addAction(actions["mode_select"])

    actions["mode_connect"] = QAction("Connect", main_window)
    actions["mode_connect"].setCheckable(True)
    actions["mode_connect"].setData("connect")
    actions["mode_connect"].toggled.connect(lambda checked: checked and main_window.set_mode("connect"))
    group.addAction(actions["mode_connect"])

    actions["mode_simulate"] = QAction("Simulate", main_window)
    actions["mode_simulate"].setCheckable(True)
    actions["mode_simulate"].setData("simulate")
    actions["mode_simulate"].setShortcut("Ctrl+G")
    actions["mode_simulate"].toggled.connect(lambda checked: checked and main_window.set_mode("simulate" if checked else None))
    group.addAction(actions["mode_simulate"])

    return actions