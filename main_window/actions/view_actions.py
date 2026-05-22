"""Ações de visualização: zoom in/out e ajustar à tela."""

from PyQt6.QtGui import QAction

def create_view_actions(main_window):

    actions = {}

    actions["zoom_in"] = QAction("Zoom In", main_window)
    actions["zoom_in"].setShortcut("Ctrl++")
    actions["zoom_in"].triggered.connect(main_window.zoom_in)

    actions["zoom_out"] = QAction("Zoom Out", main_window)
    actions["zoom_out"].setShortcut("Ctrl+-")
    actions["zoom_out"].triggered.connect(main_window.zoom_out)

    actions["zoom_fit"] = QAction("Fit to Contents", main_window)
    actions["zoom_fit"].setShortcut("Ctrl+0")
    actions["zoom_fit"].triggered.connect(main_window.zoom_to_contents)


    actions["toggle_theme"] = QAction("Light Theme", main_window)
    actions["toggle_theme"].setCheckable(True)
    actions["toggle_theme"].triggered.connect(main_window.set_light_theme)
    
    return actions