# main_window/toolbars.py
from PyQt6.QtWidgets import QToolBar

def create_toolbars(main_window, actions):
    toolbar = QToolBar("Tools", main_window)
    toolbar.setMovable(False)

    toolbar.addAction(actions["mode_add"])
    toolbar.addAction(actions["mode_delete"])
    toolbar.addAction(actions["mode_select"])

    main_window.addToolBar(toolbar)