from PyQt6.QtGui import QAction

def create_view_actions(main_window):

    actions = {}

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
    
    return actions