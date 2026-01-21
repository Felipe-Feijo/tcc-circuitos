from PyQt6.QtGui import QAction

def create_file_actions(main_window):
    actions = {}

    actions["new"] = QAction("New", main_window)
    actions["new"].setShortcut("Ctrl+N")
    actions["new"].triggered.connect(main_window.new_scene)

    actions["open"] = QAction("Open", main_window)
    actions["open"].setShortcut("Ctrl+O")
    actions["open"].triggered.connect(main_window.open_scene)

    actions["save"] = QAction("Save", main_window)
    actions["save"].setShortcut("Ctrl+S")
    actions["save"].triggered.connect(main_window.save_scene)

    actions["exit"] = QAction("Exit", main_window)
    actions["exit"].setShortcut("Ctrl+Q")
    actions["exit"].triggered.connect(main_window.close)

    return actions