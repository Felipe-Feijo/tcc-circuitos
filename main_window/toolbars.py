# main_window/toolbars.py
from PyQt6.QtWidgets import QToolBar

def create_toolbars(main_window, actions):
    toolbar = QToolBar("Tools", main_window)
    toolbar.setMovable(False)

    toolbar.addAction(actions["mode_add"])
    toolbar.addAction(actions["delete"])
    toolbar.addAction(actions["mode_select"])
    toolbar.addAction(actions["mode_connect"])

    toolbar.addSeparator()
    toolbar.addAction(actions["zoom_in"])
    toolbar.addAction(actions["zoom_out"])
    toolbar.addAction(actions["zoom_fit"])

    main_window.addToolBar(toolbar)