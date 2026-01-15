# main_window/actions.py
from PyQt6.QtGui import QAction, QIcon, QActionGroup, QKeySequence
from PyQt6.QtCore import Qt

def create_actions(main_window):
    actions = {}

    main_window.mode_group = QActionGroup(main_window)
    main_window.mode_group.setExclusive(True)

    actions["new"] = QAction("New", main_window)
    actions["new"].setShortcut("Ctrl+N")
    actions["new"].triggered.connect(main_window.new_scene)

    actions["open"] = QAction("Open", main_window)
    actions["open"].setShortcut("Ctrl+O")

    actions["save"] = QAction("Save", main_window)
    actions["save"].setShortcut("Ctrl+S")

    actions["exit"] = QAction("Exit", main_window)
    actions["exit"].setShortcut("Ctrl+Q")
    actions["exit"].triggered.connect(main_window.close)


    actions["print_graph"] = QAction("Print Graph", main_window)
    actions["print_graph"].setShortcut("Ctrl+G")
    actions["print_graph"].triggered.connect(main_window.editor_controller.build_and_print_graph)

    actions["zoom_in"] = QAction("Zoom In", main_window)
    actions["zoom_in"].setShortcut("Ctrl++")
    actions["zoom_in"].triggered.connect(main_window.zoom_in)

    actions["zoom_out"] = QAction("Zoom Out", main_window)
    actions["zoom_out"].setShortcut("Ctrl+-")
    actions["zoom_out"].triggered.connect(main_window.zoom_out)

    actions["zoom_fit"] = QAction("Fit to Contents", main_window)
    actions["zoom_fit"].setShortcut("Ctrl+0")
    actions["zoom_fit"].triggered.connect(main_window.zoom_to_contents)

    actions["delete"] = QAction("Delete", main_window)
    actions["delete"].setShortcut(QKeySequence(QKeySequence.StandardKey.Delete))
    actions["delete"].setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    actions["delete"].triggered.connect(main_window.delete_selected_items)
    

    actions["mode_add"] = QAction("Add", main_window)
    actions["mode_add"].setCheckable(True)
    actions["mode_add"].toggled.connect(lambda: main_window.set_mode("add"))
    actions["mode_add"].setIcon(QIcon("resources/icons/add-icon.png"))
    main_window.mode_group.addAction(actions["mode_add"])

    actions["mode_select"] = QAction("Select", main_window)
    actions["mode_select"].setCheckable(True)
    actions["mode_select"].toggled.connect(lambda: main_window.set_mode(None))
    main_window.mode_group.addAction(actions["mode_select"])

    actions["mode_connect"] = QAction("Connect", main_window)
    actions["mode_connect"].setCheckable(True)
    actions["mode_connect"].toggled.connect(lambda: main_window.set_mode("connect"))
    main_window.mode_group.addAction(actions["mode_connect"])

    actions["about"] = QAction("About", main_window)
    actions["about"].triggered.connect(main_window.show_about)

    
    
    


    return actions