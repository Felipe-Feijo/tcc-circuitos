"""Help actions: about and documentation."""

from PyQt6.QtGui import QAction

def create_help_actions(main_window):
    
    actions = {}

    actions["about"] = QAction("About", main_window)
    actions["about"].triggered.connect(main_window.show_about)

    return actions
