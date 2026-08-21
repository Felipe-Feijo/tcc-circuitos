"""Builds the main window toolbars from the created actions."""

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
    toolbar.addAction(actions["run"])
    toolbar.addAction(actions["step_back"])
    toolbar.addAction(actions["step_forward"])

    toolbar.addSeparator()
    toolbar.addAction(actions["speed"])
    toolbar.addAction(actions["dt"])

    main_window.addToolBar(toolbar)

    