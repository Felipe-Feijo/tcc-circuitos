from PyQt6.QtGui import QAction, QActionGroup

def create_mode_actions(main_window):
    actions = {}

    group = QActionGroup(main_window)
    group.setExclusive(True)
    main_window.mode_group = group

    actions["mode_select"] = QAction("Select", main_window)
    actions["mode_select"].setCheckable(True)
    actions["mode_select"].toggled.connect(lambda checked: checked and main_window.set_mode(None))
    group.addAction(actions["mode_select"])

    actions["mode_connect"] = QAction("Connect", main_window)
    actions["mode_connect"].setCheckable(True)
    actions["mode_connect"].toggled.connect(lambda checked: checked and main_window.set_mode("connect"))
    group.addAction(actions["mode_connect"])

    return actions