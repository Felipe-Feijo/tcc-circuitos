# main_window/toolbars.py
from PyQt6.QtWidgets import QToolBar

def create_toolbars(main_window, actions):
    toolbar = QToolBar("Tools", main_window)
    toolbar.setMovable(False)

    toolbar.addAction(actions["open_palette"])
    toolbar.addAction(actions["delete"])
    toolbar.addAction(actions["mode_select"])
    toolbar.addAction(actions["mode_connect"])

    toolbar.addSeparator()

    toolbar.addAction(actions["zoom_in"])
    toolbar.addAction(actions["zoom_out"])
    toolbar.addAction(actions["zoom_fit"])

    toolbar.addSeparator()

    toolbar.addAction(actions["mode_simulate"])

    main_window.addToolBar(toolbar)