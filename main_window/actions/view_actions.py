"""View actions: zoom in/out and fit to screen."""

from PyQt6.QtGui import QAction

def create_view_actions(main_window):

    actions = {}

    actions["zoom_in"] = QAction(main_window.tr("Zoom In"))
    actions["zoom_in"].setShortcut("Ctrl++")
    actions["zoom_in"].triggered.connect(main_window.zoom_in)

    actions["zoom_out"] = QAction(main_window.tr("Zoom Out"))
    actions["zoom_out"].setShortcut("Ctrl+-")
    actions["zoom_out"].triggered.connect(main_window.zoom_out)

    actions["zoom_fit"] = QAction(main_window.tr("Fit to Contents"))
    actions["zoom_fit"].setShortcut("Ctrl+0")
    actions["zoom_fit"].triggered.connect(main_window.zoom_to_contents)


    actions["toggle_theme"] = QAction(main_window.tr("Light Theme"))
    actions["toggle_theme"].setCheckable(True)
    actions["toggle_theme"].triggered.connect(main_window.set_light_theme)

    actions["font_size"] = QAction(main_window.tr("Font Size..."))
    actions["font_size"].triggered.connect(main_window.on_change_font_size)

    return actions